#!/usr/bin/env bash
# One-shot local billing self-test: temporary PostgreSQL + Redis + OpenCC server
# + mock upstream, then selftest.py. Everything is removed afterwards.
# Needs: go, python3, PostgreSQL server binaries, redis-server. No upstream key, no cost.
#
#   tools/opencc-billing-selftest/run-local.sh            # build the server and run
#   OPENCC_SERVER_BIN=/path/to/server tools/...run-local.sh  # reuse a built binary
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PG_PORT=55433 REDIS_PORT=56380 APP_PORT=18088 MOCK_PORT=18080
WORK="$(mktemp -d /tmp/opencc-selftest.XXXXXX)"
chmod 755 "$WORK"
PIDS=()

PG_BIN="$(pg_config --bindir 2>/dev/null || true)"
[ -x "$PG_BIN/initdb" ] || PG_BIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)"
[ -x "$PG_BIN/initdb" ] || { echo "PostgreSQL server binaries (initdb) not found"; exit 1; }
command -v redis-server >/dev/null || { echo "redis-server not found"; exit 1; }

as_pg() { if [ "$(id -u)" = 0 ]; then runuser -u postgres -- "$@"; else "$@"; fi; }

cleanup() {
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  as_pg "$PG_BIN/pg_ctl" -D "$WORK/pg" stop -m fast >/dev/null 2>&1 || true
  redis-cli -p "$REDIS_PORT" -a selftest --no-auth-warning shutdown nosave >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

wait_for() {  # url, name
  for _ in $(seq 1 90); do curl -fs -m 2 "$1" >/dev/null 2>&1 && return 0; sleep 1; done
  echo "$2 did not start; see $WORK/*.log"; tail -20 "$WORK"/*.log; exit 1
}

if [ -z "${OPENCC_SERVER_BIN:-}" ]; then
  echo "building server (API only, no embedded frontend)..."
  (cd "$ROOT/backend" && go build -o "$WORK/opencc-server" ./cmd/server)
  OPENCC_SERVER_BIN="$WORK/opencc-server"
fi

echo "starting PostgreSQL :$PG_PORT and Redis :$REDIS_PORT..."
[ "$(id -u)" = 0 ] && { mkdir -p "$WORK/pg"; chown postgres "$WORK/pg"; }
as_pg "$PG_BIN/initdb" -D "$WORK/pg" -U postgres --auth=trust >/dev/null
as_pg "$PG_BIN/pg_ctl" -D "$WORK/pg" -o "-p $PG_PORT -k /tmp" -l "$WORK/pg/postgres.log" start >/dev/null
for _ in $(seq 1 30); do psql -h 127.0.0.1 -p "$PG_PORT" -U postgres -c 'select 1' >/dev/null 2>&1 && break; sleep 1; done
psql -h 127.0.0.1 -p "$PG_PORT" -U postgres -q -c "create user opencc password 'selftest';" -c "create database opencc owner opencc;"
redis-server --port "$REDIS_PORT" --requirepass selftest --daemonize yes --dir "$WORK" --logfile "$WORK/redis.log"

python3 -I "$HERE/mock_upstream.py" --port "$MOCK_PORT" > "$WORK/mock.log" 2>&1 &
PIDS+=($!)

export OPENCC_ADMIN_EMAIL=admin@opencc.test OPENCC_ADMIN_PASSWORD="Selftest-$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n')"
(
  export AUTO_SETUP=true SERVER_HOST=127.0.0.1 SERVER_PORT="$APP_PORT" SERVER_MODE=release RUN_MODE=standard
  export DATABASE_HOST=127.0.0.1 DATABASE_PORT="$PG_PORT" DATABASE_USER=opencc DATABASE_DBNAME=opencc
  export DATABASE_PASSWORD=selftest DATABASE_SSLMODE=disable
  export REDIS_HOST=127.0.0.1 REDIS_PORT="$REDIS_PORT" REDIS_PASSWORD=selftest
  export JWT_SECRET="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  export TOTP_ENCRYPTION_KEY="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  export ADMIN_EMAIL="$OPENCC_ADMIN_EMAIL" ADMIN_PASSWORD="$OPENCC_ADMIN_PASSWORD"
  export OPENCC_CNY_PER_CREDIT=1 TZ=Asia/Shanghai DATA_DIR="$WORK/data"
  mkdir -p "$DATA_DIR"
  cd "$WORK"  # the server also writes caches relative to its working directory
  exec "$OPENCC_SERVER_BIN"
) > "$WORK/server.log" 2>&1 &
PIDS+=($!)

wait_for "http://127.0.0.1:$MOCK_PORT/v1/models" "mock upstream"
wait_for "http://127.0.0.1:$APP_PORT/health" "OpenCC server"

# The throwaway admin of this temporary instance accepts the compliance gate.
python3 -I "$HERE/selftest.py" --base "http://127.0.0.1:$APP_PORT" --mock "http://127.0.0.1:$MOCK_PORT" \
  --psql "env PGPASSWORD=selftest psql -h 127.0.0.1 -p $PG_PORT -U opencc -d opencc" \
  --accept-compliance "$@"
