package service

import (
	"github.com/Wei-Shaw/sub2api/internal/creditbilling"
	"github.com/shopspring/decimal"
	"testing"
)

func TestOpenCCCreditCommandUsesFrozenPrice(t *testing.T) {
	in := CreditSettlementInput{LocalRequestID: "local-1", Match: creditbilling.Match{RequestID: "upstream-1"}, UnitPrice: decimal.RequireFromString("0.095"), Command: UsageBillingCommand{UserID: 1, APIKeyID: 2, AccountID: 3, BalanceCost: 999, SubscriptionCost: 999, AccountQuotaCost: 999}}
	r := &creditbilling.Receipt{ID: 1, RequestID: "upstream-1", Credits: decimal.RequireFromString("2.4"), UpstreamCost: decimal.RequireFromString("0.12")}
	a, err := creditBillingCommand(in, r)
	if err != nil {
		t.Fatal(err)
	}
	if a.BalanceCost != 0.228 || a.SubscriptionCost != 0 || a.APIKeyQuotaCost != 0.228 || a.AccountQuotaCost != 0.12 {
		t.Fatalf("wrong billing amounts: %+v", a)
	}
	b, err := creditBillingCommand(in, r)
	if err != nil {
		t.Fatal(err)
	}
	if a.RequestFingerprint != b.RequestFingerprint || a.RequestID != "opencc-credit:local-1" {
		t.Fatal("unstable replay identity")
	}
	r.RequestID = "other"
	if _, err = creditBillingCommand(in, r); err == nil {
		t.Fatal("accepted mismatched receipt")
	}
}
