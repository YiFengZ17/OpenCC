package opencc

import (
	"encoding/json"
	"net/http/httptest"
	"testing"
)

func TestRegionTrustAndBoundaries(t *testing.T) {
	for _, tt := range []struct {
		remote, country, cidrs, status string
		show                           bool
	}{
		{"127.0.0.1:10", "CN", "", "unknown", false},
		{"203.0.113.1:10", "CN", "127.0.0.0/8", "unknown", false},
		{"127.0.0.1:10", "CN", "127.0.0.0/8", "known", true},
		{"[::1]:10", "CN", "::1/128", "known", true},
		{"[::ffff:127.0.0.1]:10", "CN", "127.0.0.0/8", "known", true},
		{"127.0.0.1:10", "US", "127.0.0.0/8", "known", false},
		{"127.0.0.1:10", "HK", "127.0.0.0/8", "known", false},
		{"127.0.0.1:10", "MO", "127.0.0.0/8", "known", false},
		{"127.0.0.1:10", "TW", "127.0.0.0/8", "known", false},
		{"127.0.0.1:10", "XX", "127.0.0.0/8", "unknown", false},
		{"127.0.0.1:10", "CN,US", "127.0.0.0/8", "unknown", false},
	} {
		r := ResolveRegion(tt.remote, tt.country, tt.cidrs)
		if r.Status != tt.status || r.ShowNotice != tt.show {
			t.Errorf("%+v => %+v", tt, r)
		}
		if !r.ShowNotice && r.Text != "" {
			t.Fatal("notice leaked")
		}
	}
}
func TestConfigDoesNotExposeSecretsOrUnsafeURLs(t *testing.T) {
	env := map[string]string{"OPENCC_CNY_PER_CREDIT": "NaN", "OPENCC_SHOP_10": "javascript:alert(1)", "OPENCC_SHOP_50": "https://shop.example/product/50", "UPSTREAM_API_KEY": "secret"}
	c := ConfigFromEnv(func(k string) string { return env[k] })
	if c.CNYPerCredit != 1 || c.ShopURLs["10"] != "" || c.ShopURLs["50"] == "" {
		t.Fatalf("%+v", c)
	}
}
func TestRegionResponseIsPrivate(t *testing.T) {
	t.Setenv("OPENCC_GEO_TRUSTED_PROXY_CIDRS", "127.0.0.0/8")
	req := httptest.NewRequest("GET", "/api/v1/opencc/region", nil)
	req.RemoteAddr = "127.0.0.1:1"
	req.Header.Set("CF-IPCountry", "CN")
	w := httptest.NewRecorder()
	RegionHandler(w, req)
	if w.Header().Get("Cache-Control") != "private, no-store" {
		t.Fatal("cache policy")
	}
	var body map[string]any
	if json.Unmarshal(w.Body.Bytes(), &body) != nil {
		t.Fatal("invalid json")
	}
	data := body["data"].(map[string]any)
	if data["showNotice"] != true || data["text"] != MainlandNotice {
		t.Fatal("wrong notice")
	}
	if _, ok := data["ip"]; ok {
		t.Fatal("raw IP exposed")
	}
}
