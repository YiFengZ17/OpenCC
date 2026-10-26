package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/Wei-Shaw/sub2api/internal/creditbilling"
	"github.com/shopspring/decimal"
)

// CreditSettlementService is deliberately not registered in Wire until the
// console receipt contract and request ID correspondence have been verified.
// It uses the existing money-event ledger; replay after a crash cannot charge twice.
type CreditSettlementService struct {
	DB         *sql.DB
	Console    *creditbilling.Console
	Ledger     UsageBillingRepository
	Invalidate func(context.Context, int64, int64) error
}

type CreditSettlementInput struct {
	LocalRequestID string
	Match          creditbilling.Match
	UnitPrice      decimal.Decimal
	Command        UsageBillingCommand
}

// Enqueue snapshots the price and billing identity. Call only after a durable
// preflight reservation and a verified upstream request ID have been recorded.
func (s *CreditSettlementService) Enqueue(ctx context.Context, in CreditSettlementInput) error {
	if s.DB == nil || in.LocalRequestID == "" || in.Match.RequestID == "" || in.Match.APIKeyID <= 0 || in.Match.GroupID <= 0 || in.Match.Model == "" || in.Match.StartedAt.IsZero() || in.Command.APIKeyID <= 0 || in.Command.UserID <= 0 || in.Command.AccountID <= 0 || in.Command.SubscriptionID != nil || in.Command.BillingType != BillingTypeBalance {
		return errors.New("invalid credit settlement identity")
	}
	if _, err := creditbilling.Charge(decimal.Zero, in.UnitPrice); err != nil {
		return err
	}
	// Token prices must never leak into a credit charge.
	in.Command.RequestID = "opencc-credit:" + in.LocalRequestID
	in.Command.RequestFingerprint = ""
	in.Command.BalanceCost = 0
	in.Command.SubscriptionCost = 0
	in.Command.APIKeyQuotaCost = 0
	in.Command.APIKeyRateLimitCost = 0
	in.Command.AccountQuotaCost = 0
	payload, err := json.Marshal(in)
	if err != nil {
		return err
	}
	result, err := s.DB.ExecContext(ctx, `INSERT INTO opencc_credit_settlements (request_id, api_key_id, user_id, upstream_request_id, upstream_api_key_id, input, status, next_attempt_at) VALUES ($1,$2,$3,$4,$5,$6,'pending',NOW()) ON CONFLICT (request_id,api_key_id) DO NOTHING`, in.LocalRequestID, in.Command.APIKeyID, in.Command.UserID, in.Match.RequestID, in.Match.APIKeyID, payload)
	if err != nil {
		return err
	}
	n, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if n == 1 {
		return nil
	}
	var existing []byte
	if err = s.DB.QueryRowContext(ctx, `SELECT input FROM opencc_credit_settlements WHERE request_id=$1 AND api_key_id=$2`, in.LocalRequestID, in.Command.APIKeyID).Scan(&existing); err != nil {
		return err
	}
	var old CreditSettlementInput
	if json.Unmarshal(existing, &old) != nil {
		return errors.New("invalid stored credit settlement")
	}
	canonical, _ := json.Marshal(old)
	if string(canonical) != string(payload) {
		return ErrUsageBillingRequestConflict
	}
	return nil
}

// ProcessOne claims one durable job with a lease. Only expired leases can be
// reclaimed; all writes compare the claim version to exclude stale workers.
func (s *CreditSettlementService) ProcessOne(ctx context.Context) (bool, error) {
	if s.DB == nil || s.Console == nil || s.Ledger == nil || s.Invalidate == nil {
		return false, errors.New("credit settlement dependencies unavailable")
	}
	var id, version int64
	var inputBytes, commandBytes []byte
	var created time.Time
	err := s.DB.QueryRowContext(ctx, `UPDATE opencc_credit_settlements SET lease_until=NOW()+INTERVAL '2 minutes',version=version+1,attempts=attempts+1 WHERE id=(SELECT id FROM opencc_credit_settlements WHERE status IN ('pending','ready') AND next_attempt_at<=NOW() AND (lease_until IS NULL OR lease_until<NOW()) ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id,version,input,billing_command,created_at`).Scan(&id, &version, &inputBytes, &commandBytes, &created)
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	var in CreditSettlementInput
	if json.Unmarshal(inputBytes, &in) != nil {
		return true, s.deferJob(ctx, id, version, "invalid_stored_input", true)
	}
	var cmd UsageBillingCommand
	if len(commandBytes) > 0 {
		if json.Unmarshal(commandBytes, &cmd) != nil {
			return true, s.deferJob(ctx, id, version, "invalid_stored_command", true)
		}
	} else {
		receipt, err := s.Console.Lookup(ctx, in.Match)
		if err != nil {
			code := "upstream_unavailable"
			manual := time.Since(created) > 24*time.Hour
			switch {
			case errors.Is(err, creditbilling.ErrAuthentication):
				code = "console_authentication_required"
			case errors.Is(err, creditbilling.ErrPending):
				code = "awaiting_upstream_usage"
			case errors.Is(err, creditbilling.ErrContract):
				code = "credit_contract_mismatch"
				manual = true
			case errors.Is(err, creditbilling.ErrAmbiguous):
				code = "ambiguous_upstream_request"
				manual = true
			}
			return true, s.deferJob(ctx, id, version, code, manual)
		}
		cmd, err = creditBillingCommand(in, receipt)
		if err != nil {
			return true, s.deferJob(ctx, id, version, "invalid_credit_amount", true)
		}
		encoded, _ := json.Marshal(cmd)
		// Persist the exact immutable monetary command BEFORE the ledger call.
		result, err := s.DB.ExecContext(ctx, `UPDATE opencc_credit_settlements SET billing_command=$1,credits=$2,unit_price=$3,upstream_cost=$4,upstream_usage_id=$5,status='ready',last_error=NULL WHERE id=$6 AND version=$7`, encoded, receipt.Credits.String(), in.UnitPrice.String(), receipt.UpstreamCost.String(), receipt.ID, id, version)
		if err != nil {
			return true, err
		}
		n, _ := result.RowsAffected()
		if n != 1 {
			return true, errors.New("credit lease lost")
		}
	}
	if _, err := s.Ledger.Apply(ctx, &cmd); err != nil {
		return true, s.deferJob(ctx, id, version, "ledger_apply_failed", errors.Is(err, ErrUsageBillingRequestConflict))
	}
	// Retry cache invalidation even if the ledger reports an already-applied event.
	if err := s.Invalidate(ctx, cmd.UserID, cmd.APIKeyID); err != nil {
		return true, s.deferJob(ctx, id, version, "cache_invalidation_failed", false)
	}
	_, err = s.DB.ExecContext(ctx, `UPDATE opencc_credit_settlements SET status='settled',settled_at=NOW(),lease_until=NULL,last_error=NULL WHERE id=$1 AND version=$2`, id, version)
	return true, err
}

func creditBillingCommand(in CreditSettlementInput, receipt *creditbilling.Receipt) (UsageBillingCommand, error) {
	if receipt == nil || receipt.ID <= 0 || receipt.RequestID != in.Match.RequestID {
		return UsageBillingCommand{}, creditbilling.ErrContract
	}
	amount, err := creditbilling.Charge(receipt.Credits, in.UnitPrice)
	if err != nil {
		return UsageBillingCommand{}, err
	}
	cmd := in.Command
	cmd.RequestID = "opencc-credit:" + in.LocalRequestID
	cmd.RequestFingerprint = ""
	cmd.BalanceCost, _ = amount.Float64()
	cmd.APIKeyQuotaCost = cmd.BalanceCost
	cmd.APIKeyRateLimitCost = cmd.BalanceCost
	cmd.SubscriptionCost = 0
	cmd.AccountQuotaCost, _ = receipt.UpstreamCost.Round(8).Float64()
	cmd.Normalize()
	return cmd, nil
}

func (s *CreditSettlementService) deferJob(ctx context.Context, id, version int64, code string, manual bool) error {
	status := "pending"
	if manual {
		status = "review"
	}
	// Preserve a prepared command through retries; never recalculate historical prices.
	_, err := s.DB.ExecContext(ctx, `UPDATE opencc_credit_settlements SET status=CASE WHEN $1='review' THEN 'review' WHEN billing_command IS NOT NULL THEN 'ready' ELSE 'pending' END,last_error=$2,lease_until=NULL,next_attempt_at=NOW()+INTERVAL '1 minute' WHERE id=$3 AND version=$4`, status, code, id, version)
	if err != nil {
		return fmt.Errorf("persist credit retry: %w", err)
	}
	return nil
}
