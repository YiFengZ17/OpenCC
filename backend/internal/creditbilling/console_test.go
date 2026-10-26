package creditbilling

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/shopspring/decimal"
)

func sampleRow(t *testing.T, extra string) map[string]json.RawMessage {
	t.Helper()
	var row map[string]json.RawMessage
	err := json.Unmarshal([]byte(`{"id":123,"request_id":"req-1","api_key_id":12,"group_id":22,"model":"claude-test","billing_mode":"kiro_credit","verified_test_credit":"2.40","actual_cost":"0.228"`+extra+`}`), &row)
	if err != nil {
		t.Fatal(err)
	}
	return row
}

func TestCreditContract(t *testing.T) {
	c := Contract{CreditField: "verified_test_credit", RequestIDField: "request_id", SettledMode: "kiro_credit"}
	m := Match{RequestID: "req-1", APIKeyID: 12, GroupID: 22, Model: "claude-test"}
	r, err := ParseReceipt(sampleRow(t, ""), c, m)
	if err != nil {
		t.Fatal(err)
	}
	amount, err := Charge(r.Credits, decimal.RequireFromString("0.095"))
	if err != nil || amount.String() != "0.228" {
		t.Fatalf("charge=%s err=%v", amount, err)
	}
	for name, mutate := range map[string]func(map[string]json.RawMessage){
		"missing credits":   func(r map[string]json.RawMessage) { delete(r, "verified_test_credit") },
		"foreign key":       func(r map[string]json.RawMessage) { r["api_key_id"] = json.RawMessage(`99`) },
		"different request": func(r map[string]json.RawMessage) { r["request_id"] = json.RawMessage(`"other"`) },
		"negative":          func(r map[string]json.RawMessage) { r["verified_test_credit"] = json.RawMessage(`-1`) },
		"exponent":          func(r map[string]json.RawMessage) { r["verified_test_credit"] = json.RawMessage(`"1e99999999"`) },
		"token billing":     func(r map[string]json.RawMessage) { r["billing_mode"] = json.RawMessage(`"token"`) },
	} {
		t.Run(name, func(t *testing.T) {
			row := sampleRow(t, "")
			mutate(row)
			if _, err := ParseReceipt(row, c, m); !errors.Is(err, ErrContract) {
				t.Fatalf("got %v", err)
			}
		})
	}
	row := sampleRow(t, "")
	row["billing_mode"] = json.RawMessage(`"kiro_credit_missing"`)
	if _, err := ParseReceipt(row, c, m); !errors.Is(err, ErrPending) {
		t.Fatal(err)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestLookupRejectsDuplicateAndAuthentication(t *testing.T) {
	for _, tc := range []struct {
		name, body string
		status     int
		want       error
	}{
		{"duplicate", `{"code":0,"data":{"total":2,"items":[ROW,ROW]}}`, 200, ErrAmbiguous},
		{"unauthorized", `{}`, 401, ErrAuthentication},
		{"empty", `{"code":0,"data":{"total":0,"items":[]}}`, 200, ErrPending},
		{"schema changed", `{"code":0,"data":{"records":[]}}`, 200, ErrContract},
	} {
		t.Run(tc.name, func(t *testing.T) {
			row, _ := json.Marshal(sampleRow(t, ""))
			body := strings.ReplaceAll(tc.body, "ROW", string(row))
			client := Console{BaseURL: "https://console.supergpt.dev", Token: func(context.Context) (string, error) { return "test-secret", nil }, Contract: Contract{"verified_test_credit", "request_id", "kiro_credit"}, HTTP: &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
				if r.Header.Get("Authorization") != "Bearer test-secret" || r.URL.Query().Get("api_key_id") != "12" {
					t.Fatal("missing auth or key filter")
				}
				return &http.Response{StatusCode: tc.status, Body: io.NopCloser(strings.NewReader(body)), Header: make(http.Header)}, nil
			})}}
			_, err := client.Lookup(context.Background(), Match{"req-1", 12, 22, "claude-test", time.Now()})
			if !errors.Is(err, tc.want) {
				t.Fatalf("got %v want %v", err, tc.want)
			}
		})
	}
}

func TestLookupRejectsRedirect(t *testing.T) {
	calls := 0
	c := Console{BaseURL: "https://console.supergpt.dev", Token: func(context.Context) (string, error) { return "secret", nil }, Contract: Contract{"credits", "request_id", "kiro_credit"}, HTTP: &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 302, Header: http.Header{"Location": []string{"https://other.example/"}}, Body: io.NopCloser(strings.NewReader(""))}, nil
	})}}
	_, err := c.Lookup(context.Background(), Match{"req-1", 12, 22, "claude-test", time.Now()})
	if err == nil || calls != 1 {
		t.Fatalf("redirect followed: calls=%d err=%v", calls, err)
	}
}

func TestChargeRounding(t *testing.T) {
	got, err := Charge(decimal.RequireFromString("0.01"), decimal.RequireFromString("0.095"))
	if err != nil || got.String() != "0.00095" {
		t.Fatalf("%s %v", got, err)
	}
}
