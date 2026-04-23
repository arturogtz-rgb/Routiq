# Routiq Auth Testing Playbook

## Credentials seeded on startup
- **Super Admin (Master):** `owner@routiq.mx` / `Routiq2026!`
- **Demo Company Admin (Aventúrate por Jalisco):** `admin@aventurate.mx` / `Demo2026!`
- **Demo Executive:** `ejecutivo@aventurate.mx` / `Demo2026!`

## Endpoints
- POST `/api/auth/login` — body: `{email, password}` → returns user + sets cookies
- GET `/api/auth/me` — returns current user
- POST `/api/auth/logout` — clears cookies
- POST `/api/auth/refresh` — refreshes access token
- POST `/api/companies` — super_admin only, creates tenant + admin user
- POST `/api/users/invite-executive` — company_admin only, creates executive in own tenant

## Quick curl test
```
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
curl -c /tmp/c.txt -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@aventurate.mx","password":"Demo2026!"}'
curl -b /tmp/c.txt "$API/api/auth/me"
```

## Role-based access
- `super_admin`: Master panel, create/suspend companies, global metrics. No access to tenant data.
- `company_admin`: Full tenant access, pricing config, team, catalogs, quotations.
- `executive`: Own quotations, read catalogs, Kanban.
