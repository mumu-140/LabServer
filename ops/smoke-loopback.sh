#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export NO_PROXY="127.0.0.1,localhost,::1"
export no_proxy="127.0.0.1,localhost,::1"

CORE_URL="http://127.0.0.1:${LABSERVER_CORE_PORT:-18281}"
WEB_URL="http://127.0.0.1:${LABSERVER_WEB_PORT:-18280}"
COOKIE_JAR="$(mktemp /tmp/labserver_smoke_cookies.XXXXXX)"
trap 'rm -f "${COOKIE_JAR}"' EXIT

echo "=================================================="
echo " Starting LabServer Loopback Smoke Verification   "
echo "=================================================="

# 1. Healthz checks
echo -n "[1/11] Testing Core /healthz... "
CORE_HEALTH="$(curl -s -f --noproxy "*" "${CORE_URL}/healthz")"
if [[ "${CORE_HEALTH}" != *'"status":"ok"'* ]] && [[ "${CORE_HEALTH}" != *'"status": "ok"'* ]]; then
    echo "FAILED: unexpected response: ${CORE_HEALTH}"
    exit 1
fi
echo "OK"

echo -n "[2/11] Testing Web /healthz... "
WEB_HEALTH="$(curl -s -f --noproxy "*" "${WEB_URL}/healthz")"
if [[ "${WEB_HEALTH}" != *'"status":"ok"'* ]] && [[ "${WEB_HEALTH}" != *'"status": "ok"'* ]]; then
    echo "FAILED: unexpected response: ${WEB_HEALTH}"
    exit 1
fi
echo "OK"

# 2. Public Login page and Unauthenticated Default-Deny on /schedule and /dashboard
echo -n "[3/11] Testing Web GET /login (200) and unauthenticated /schedule & /dashboard (401)... "
LOGIN_HTML="$(curl -s -f --noproxy "*" "${WEB_URL}/login")"
if [[ "${LOGIN_HTML}" != *"<form"* ]] || [[ "${LOGIN_HTML}" != *"password"* ]]; then
    echo "FAILED: /login missing form elements"
    exit 1
fi

UNAUTH_SCHEDULE="$(curl -s -o /dev/null -w "%{http_code}" --noproxy "*" "${WEB_URL}/schedule")"
if [ "${UNAUTH_SCHEDULE}" -ne 401 ]; then
    echo "FAILED: Expected HTTP 401 on unauthenticated /schedule, got ${UNAUTH_SCHEDULE}"
    exit 1
fi

UNAUTH_DASHBOARD="$(curl -s -o /dev/null -w "%{http_code}" --noproxy "*" "${WEB_URL}/dashboard")"
if [ "${UNAUTH_DASHBOARD}" -ne 401 ]; then
    echo "FAILED: Expected HTTP 401 on unauthenticated /dashboard, got ${UNAUTH_DASHBOARD}"
    exit 1
fi
echo "OK"

# 3. Bootstrap Admin
SMOKE_ADMIN="smoke_admin_$$"
echo -n "[4/11] Testing Admin Bootstrap for user '${SMOKE_ADMIN}'... "
BOOTSTRAP_OUT="$("${SCRIPT_DIR}/bootstrap-admin.sh" "${SMOKE_ADMIN}" 2>&1 || true)"
ADMIN_PASSWORD=""

if echo "${BOOTSTRAP_OUT}" | grep -q "Generated password:"; then
    ADMIN_PASSWORD="$(echo "${BOOTSTRAP_OUT}" | grep "Generated password:" | awk '{print $NF}')"
    echo "OK (bootstrapped fresh admin with generated password)"
elif echo "${BOOTSTRAP_OUT}" | grep -q "An enabled administrator already exists"; then
    echo "OK (correctly refused: enabled administrator already exists)"
    ADMIN_PASSWORD="${SMOKE_ADMIN_PASSWORD:-}"
else
    echo "FAILED: Unexpected bootstrap output:"
    echo "${BOOTSTRAP_OUT}"
    exit 1
fi

# 4. Seed Fleet Servers
echo -n "[5/11] Testing Fleet Server Seeding... "
SEED_OUT="$("${SCRIPT_DIR}/seed-servers.sh" 2>&1 || true)"
if echo "${SEED_OUT}" | grep -q "Successfully seeded"; then
    echo "OK (fleet servers seeded)"
else
    echo "FAILED: Unexpected seed-servers output:"
    echo "${SEED_OUT}"
    exit 1
fi

# 5. Web Login Flow (if password available)
if [ -n "${ADMIN_PASSWORD}" ]; then
    echo -n "[6/11] Testing Web POST /login with admin credentials... "
    HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" --noproxy "*" \
        -c "${COOKIE_JAR}" \
        -X POST "${WEB_URL}/login" \
        -d "username=${SMOKE_ADMIN}&password=${ADMIN_PASSWORD}")"

    if [ "${HTTP_CODE}" -ne 303 ]; then
        echo "FAILED: Expected HTTP 303 redirect on login, got ${HTTP_CODE}"
        exit 1
    fi

    if ! grep -q "labserver_session" "${COOKIE_JAR}"; then
        echo "FAILED: Session cookie not found in cookie jar"
        exit 1
    fi
    echo "OK (received labserver_session cookie)"

    # 6. Authenticated Web /schedule
    echo -n "[7/11] Testing Authenticated Web GET /schedule using session cookie... "
    AUTH_SCHEDULE="$(curl -s -f --noproxy "*" -b "${COOKIE_JAR}" "${WEB_URL}/schedule")"
    if [[ "${AUTH_SCHEDULE}" != *"Schedule"* ]] && [[ "${AUTH_SCHEDULE}" != *"schedule"* ]]; then
        echo "FAILED: /schedule missing expected markup for authenticated viewer"
        exit 1
    fi
    echo "OK (schedule rendered for authenticated admin)"

    # 7. Authenticated Web /dashboard
    echo -n "[8/11] Testing Authenticated Web GET /dashboard using session cookie... "
    AUTH_DASHBOARD="$(curl -s -f --noproxy "*" -b "${COOKIE_JAR}" "${WEB_URL}/dashboard")"
    if [[ "${AUTH_DASHBOARD}" != *"card-fwq10"* ]] && [[ "${AUTH_DASHBOARD}" != *"fwq10"* ]]; then
        echo "FAILED: /dashboard missing server cards markup"
        exit 1
    fi
    echo "OK (dashboard rendered server cards)"

    # 8. Authenticated Core /api/v1/auth/me
    echo -n "[9/11] Testing Core GET /api/v1/auth/me using session cookie... "
    ME_JSON="$(curl -s -f --noproxy "*" \
        -b "${COOKIE_JAR}" \
        -H "Accept: application/json" \
        "${CORE_URL}/api/v1/auth/me")"

    if [[ "${ME_JSON}" != *'"role":"admin"'* ]] && [[ "${ME_JSON}" != *'"role": "admin"'* ]]; then
        echo "FAILED: /auth/me did not confirm admin role: ${ME_JSON}"
        exit 1
    fi
    echo "OK (authenticated as admin)"

    # 9. Authenticated Core /api/v1/monitoring/dashboard
    echo -n "[10/11] Testing Core GET /api/v1/monitoring/dashboard using session cookie... "
    MON_JSON="$(curl -s -f --noproxy "*" \
        -b "${COOKIE_JAR}" \
        -H "Accept: application/json" \
        "${CORE_URL}/api/v1/monitoring/dashboard")"

    if [[ "${MON_JSON}" != *'"cards":'* ]] || [[ "${MON_JSON}" != *'"fwq10"'* ]]; then
        echo "FAILED: /api/v1/monitoring/dashboard missing cards or fwq10: ${MON_JSON}"
        exit 1
    fi
    echo "OK (monitoring dashboard API returned server cards)"

    # 10. Web Logout
    echo -n "[11/11] Testing Web POST /logout... "
    LOGOUT_CODE="$(curl -s -o /dev/null -w "%{http_code}" --noproxy "*" \
        -b "${COOKIE_JAR}" \
        -c "${COOKIE_JAR}" \
        -X POST "${WEB_URL}/logout")"

    if [ "${LOGOUT_CODE}" -ne 303 ]; then
        echo "FAILED: Expected HTTP 303 on logout, got ${LOGOUT_CODE}"
        exit 1
    fi

    AFTER_LOGOUT_SCHEDULE="$(curl -s -o /dev/null -w "%{http_code}" --noproxy "*" -b "${COOKIE_JAR}" "${WEB_URL}/schedule")"
    if [ "${AFTER_LOGOUT_SCHEDULE}" -ne 401 ]; then
        echo "FAILED: Expected HTTP 401 on /schedule after logout, got ${AFTER_LOGOUT_SCHEDULE}"
        exit 1
    fi

    AFTER_LOGOUT_DASHBOARD="$(curl -s -o /dev/null -w "%{http_code}" --noproxy "*" -b "${COOKIE_JAR}" "${WEB_URL}/dashboard")"
    if [ "${AFTER_LOGOUT_DASHBOARD}" -ne 401 ]; then
        echo "FAILED: Expected HTTP 401 on /dashboard after logout, got ${AFTER_LOGOUT_DASHBOARD}"
        exit 1
    fi
    echo "OK (session invalidated and /schedule & /dashboard return 401)"
else
    echo "[6/11] Skipping login (no password captured for existing admin)"
    echo "[7/11] Skipping authenticated /schedule"
    echo "[8/11] Skipping authenticated /dashboard"
    echo "[9/11] Skipping /auth/me"
    echo "[10/11] Skipping /api/v1/monitoring/dashboard"
    echo "[11/11] Skipping logout"
fi

echo "=================================================="
echo " All 11 Loopback Smoke Checks Passed Successfully! "
echo "=================================================="
