// Package opencc provides the public integration boundary for the OpenCC console.
// It does not handle money, authentication, or gateway traffic: Sub2API owns those.
package opencc

import (
	"encoding/json"
	"math"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"strconv"
	"strings"
)

const MainlandNotice = "我司检测到您的 IP 地址来源于中国大陆，此在我们所授权的可访问的服务地区以外，仅授权大陆模型转发权限。我司不会以任何形式存储您的信息，仅提供面向模型服务提供商的转发能力。请您务必知晓我司用户协议与您所在地区的相关法规并取得相关授权，我司不对您的任何行为负责。"

type PublicConfig struct {
	Brand        string            `json:"brand"`
	CNYPerCredit float64           `json:"cny_per_credit"`
	Amounts      []int             `json:"amounts"`
	ShopURLs     map[string]string `json:"shop_urls"`
	SupportURL   string            `json:"support_url"`
	GatewayURL   string            `json:"gateway_url"`
}
type Region struct {
	ShowNotice bool   `json:"showNotice"`
	Status     string `json:"status"`
	Text       string `json:"text"`
}

func SafeURL(value string) string {
	u, err := url.Parse(strings.TrimSpace(value))
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil {
		return ""
	}
	return u.String()
}
func ConfigFromEnv(getenv func(string) string) PublicConfig {
	rate, err := strconv.ParseFloat(getenv("OPENCC_CNY_PER_CREDIT"), 64)
	if err != nil || rate <= 0 || math.IsNaN(rate) || math.IsInf(rate, 0) {
		rate = 1
	}
	shops := map[string]string{}
	for _, amount := range []int{10, 50, 100, 200} {
		key := strconv.Itoa(amount)
		if value := SafeURL(getenv("OPENCC_SHOP_" + key)); value != "" {
			shops[key] = value
		}
	}
	return PublicConfig{"OpenCC", rate, []int{10, 50, 100, 200}, shops, SafeURL(getenv("OPENCC_SUPPORT_URL")), SafeURL(getenv("OPENCC_GATEWAY_URL"))}
}

// ResolveRegion only trusts country headers on an explicitly configured immediate peer.
// The trusted reverse proxy MUST sanitize these headers before forwarding.
func ResolveRegion(remote, country, cidrs string) Region {
	result := Region{false, "unknown", ""}
	host, _, err := net.SplitHostPort(remote)
	if err != nil {
		return result
	}
	ip, err := netip.ParseAddr(host)
	if err != nil {
		return result
	}
	ip = ip.Unmap()
	trusted := false
	for _, raw := range strings.Split(cidrs, ",") {
		prefix, err := netip.ParsePrefix(strings.TrimSpace(raw))
		if err == nil && prefix.Contains(ip) {
			trusted = true
			break
		}
	}
	country = strings.ToUpper(strings.TrimSpace(country))
	if !trusted || len(country) != 2 || country == "XX" || country == "T1" ||
		country[0] < 'A' || country[0] > 'Z' || country[1] < 'A' || country[1] > 'Z' {
		return result
	}
	result.Status = "known"
	if country == "CN" {
		result.ShowNotice = true
		result.Text = MainlandNotice
	}
	return result
}
func respond(w http.ResponseWriter, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "private, no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	_ = json.NewEncoder(w).Encode(map[string]any{"code": 0, "data": data})
}
func ConfigHandler(w http.ResponseWriter, r *http.Request) { respond(w, ConfigFromEnv(os.Getenv)) }
func RegionHandler(w http.ResponseWriter, r *http.Request) {
	respond(w, ResolveRegion(r.RemoteAddr, r.Header.Get("CF-IPCountry"), os.Getenv("OPENCC_GEO_TRUSTED_PROXY_CIDRS")))
}
