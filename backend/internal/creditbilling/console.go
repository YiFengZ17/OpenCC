// Package creditbilling reconciles credit usage with an upstream console.
// Credit field names are an explicit deployment contract, never guessed from costs.
package creditbilling

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/shopspring/decimal"
)

var (
	ErrAuthentication = errors.New("upstream console session expired or unauthorized")
	ErrPending        = errors.New("upstream usage is not settled")
	ErrContract       = errors.New("upstream usage does not match the verified credit contract")
	ErrAmbiguous      = errors.New("multiple upstream records match this request")
)

// Contract must be verified against an authenticated response before enabling billing.
type Contract struct {
	CreditField    string
	RequestIDField string
	SettledMode    string
}

type Match struct {
	RequestID string
	APIKeyID  int64
	GroupID   int64
	Model     string
	StartedAt time.Time
}

type Receipt struct {
	ID           int64
	RequestID    string
	Credits      decimal.Decimal
	UpstreamCost decimal.Decimal
}

type Console struct {
	BaseURL  string
	Token    func(context.Context) (string, error)
	Contract Contract
	HTTP     *http.Client
	MaxPages int
}

func (c *Console) Lookup(ctx context.Context, match Match) (*Receipt, error) {
	base, err := url.Parse(c.BaseURL)
	if err != nil || base.Scheme != "https" || base.Host != "console.supergpt.dev" || base.User != nil || base.RawQuery != "" || base.Fragment != "" || (base.Path != "" && base.Path != "/") {
		return nil, fmt.Errorf("invalid SuperGPT console origin")
	}
	if c.Token == nil || c.Contract.CreditField == "" || c.Contract.RequestIDField == "" || c.Contract.SettledMode != "kiro_credit" || match.RequestID == "" || match.APIKeyID <= 0 || match.GroupID <= 0 || match.Model == "" || match.StartedAt.IsZero() {
		return nil, ErrContract
	}
	token, err := c.Token(ctx)
	if err != nil || strings.TrimSpace(token) == "" {
		return nil, ErrAuthentication
	}
	client := &http.Client{Timeout: 20 * time.Second}
	if c.HTTP != nil {
		clone := *c.HTTP
		client = &clone
	}
	// Never send the console bearer token to a redirected destination.
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	if client.Timeout == 0 {
		client.Timeout = 20 * time.Second
	}
	pages := c.MaxPages
	if pages <= 0 {
		pages = 10
	}
	var found *Receipt
	for page := 1; page <= pages; page++ {
		q := url.Values{"page": {strconv.Itoa(page)}, "page_size": {"100"}, "api_key_id": {strconv.FormatInt(match.APIKeyID, 10)}, "group_id": {strconv.FormatInt(match.GroupID, 10)}, "timezone": {"UTC"}, "start_date": {match.StartedAt.UTC().Add(-24 * time.Hour).Format("2006-01-02")}, "end_date": {time.Now().UTC().Format("2006-01-02")}}
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, strings.TrimSuffix(c.BaseURL, "/")+"/api/v1/usage?"+q.Encode(), nil)
		req.Header.Set("Authorization", "Bearer "+token)
		resp, err := client.Do(req)
		if err != nil {
			return nil, errors.New("upstream usage query failed")
		}
		body, readErr := io.ReadAll(io.LimitReader(resp.Body, 4<<20+1))
		resp.Body.Close()
		if resp.StatusCode == 401 || resp.StatusCode == 403 {
			return nil, ErrAuthentication
		}
		if resp.StatusCode != 200 || readErr != nil || len(body) > 4<<20 {
			return nil, errors.New("upstream usage query returned an invalid response")
		}
		var envelope struct {
			Code int `json:"code"`
			Data struct {
				Items []map[string]json.RawMessage `json:"items"`
				Total *int                         `json:"total"`
			} `json:"data"`
		}
		if json.Unmarshal(body, &envelope) != nil || envelope.Code != 0 || envelope.Data.Total == nil || *envelope.Data.Total < 0 {
			return nil, ErrContract
		}
		for _, row := range envelope.Data.Items {
			var id string
			if json.Unmarshal(row[c.Contract.RequestIDField], &id) != nil || id != match.RequestID {
				continue
			}
			if found != nil {
				return nil, ErrAmbiguous
			}
			receipt, err := ParseReceipt(row, c.Contract, match)
			if err != nil {
				return nil, err
			}
			found = receipt
		}
		if page*100 >= *envelope.Data.Total {
			if found == nil {
				return nil, ErrPending
			}
			return found, nil
		}
		if len(envelope.Data.Items) == 0 {
			return nil, ErrContract
		}
	}
	// An incomplete scan cannot establish a unique association.
	return nil, errors.New("upstream usage pagination limit reached")
}

func ParseReceipt(row map[string]json.RawMessage, contract Contract, match Match) (*Receipt, error) {
	var mode, requestID, model string
	var id, keyID, groupID int64
	if json.Unmarshal(row["id"], &id) != nil || id <= 0 || json.Unmarshal(row["api_key_id"], &keyID) != nil || json.Unmarshal(row["group_id"], &groupID) != nil || json.Unmarshal(row[contract.RequestIDField], &requestID) != nil || json.Unmarshal(row["model"], &model) != nil || keyID != match.APIKeyID || groupID != match.GroupID || model != match.Model || requestID != match.RequestID {
		return nil, ErrContract
	}
	if json.Unmarshal(row["billing_mode"], &mode) != nil {
		return nil, ErrContract
	}
	if mode == "kiro_credit_missing" || mode == "kiro_credit_error" {
		return nil, ErrPending
	}
	if mode != contract.SettledMode || mode != "kiro_credit" {
		return nil, ErrContract
	}
	credits, err := readDecimal(row[contract.CreditField])
	if err != nil {
		return nil, ErrContract
	}
	cost, err := readDecimal(row["actual_cost"])
	if err != nil {
		return nil, ErrContract
	}
	return &Receipt{ID: id, RequestID: requestID, Credits: credits, UpstreamCost: cost}, nil
}

func readDecimal(raw json.RawMessage) (decimal.Decimal, error) {
	s := strings.TrimSpace(string(raw))
	if strings.HasPrefix(s, "\"") {
		if json.Unmarshal(raw, &s) != nil {
			return decimal.Zero, ErrContract
		}
	}
	if len(s) == 0 || len(s) > 40 {
		return decimal.Zero, ErrContract
	}
	// Avoid unbounded exponents and prohibit signs, NaN, scientific notation.
	for _, r := range s {
		if (r < '0' || r > '9') && r != '.' {
			return decimal.Zero, ErrContract
		}
	}
	d, err := decimal.NewFromString(s)
	if err != nil || d.IsNegative() || d.GreaterThan(decimal.NewFromInt(1000000000)) {
		return decimal.Zero, ErrContract
	}
	return d, nil
}

// Charge accepts already-metered credits. No token or model multiplier is applied.
func Charge(credits, unitPrice decimal.Decimal) (decimal.Decimal, error) {
	if credits.IsNegative() || unitPrice.IsNegative() || unitPrice.IsZero() || credits.GreaterThan(decimal.NewFromInt(1000000000)) || unitPrice.GreaterThan(decimal.NewFromInt(1000000)) {
		return decimal.Zero, ErrContract
	}
	return credits.Mul(unitPrice).Round(8), nil
}
