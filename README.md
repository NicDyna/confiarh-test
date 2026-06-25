# ConfiaRH — Customer Portal (demo)

A small, **read-only** dashboard that lets ConfiaRH's customers log in and see
the job openings ConfiaRH is recruiting for on their behalf, plus the applicants
behind each opening.

It reads from Odoo through the external XML-RPC API. It never writes, creates,
or deletes anything.

## How it works

1. A customer logs in with the **email** and **PIN** stored on their
   `res.partner` record (`email` + `x_studio_pin`).
2. The app looks up that partner and lists every `hr.job` whose customer field
   (`x_studio_many2one_field_5j_1jrv1qb8f`) points to that partner (or its parent
   company).
3. Clicking a job shows the `hr.applicant` records linked to it.

## What you need in Odoo

- **`res.partner`** → integer field `x_studio_pin` (the login PIN), and the
  partner must have an `email`.
- **`hr.job`** → many2one field `x_studio_many2one_field_5j_1jrv1qb8f` pointing
  to the customer (`res.partner`).
- **An API user** with read access to `res.partner`, `hr.job`, and `hr.applicant`.
  Generate an API key for that user: *Settings → Users → (user) → Account
  Security → New API Key*.

> Tip: for a real deployment, use a dedicated internal user limited to read
> access on just those models.

## Railway variables

Set these under **Railway → your service → Variables**:

| Variable        | Example                          | Required |
|-----------------|----------------------------------|----------|
| `ODOO_URL`      | `https://confiarh.odoo.com`      | yes      |
| `ODOO_DB`       | `confiarh`                       | yes      |
| `ODOO_USERNAME` | `api-user@confiarh.lu`           | yes      |
| `ODOO_API_KEY`  | *(the API key)*                  | yes      |
| `PARTNER_PIN_FIELD` | `x_studio_pin`               | no (default) |
| `JOB_PARTNER_FIELD` | `x_studio_many2one_field_5j_1jrv1qb8f` | no (default) |
| `SECRET_KEY`    | any string                       | no       |

`ODOO_USERNAME` is the **API user** the app authenticates as — not the
customer's login. Customers always log in with their own email + PIN.

## Deploy on Railway

1. Put these files in a GitHub repo (drag-and-drop the folder contents into the
   repo via the GitHub web UI).
2. In Railway: **New Project → Deploy from GitHub repo**, pick the repo.
3. Add the variables above.
4. Railway builds from `requirements.txt` and starts the app with the `Procfile`.
5. Open the generated URL and log in with a test partner's email + PIN.

## Run locally (optional)

```bash
pip install -r requirements.txt
export ODOO_URL=https://your-db.odoo.com
export ODOO_DB=your-db
export ODOO_USERNAME=api-user@confiarh.lu
export ODOO_API_KEY=your-key
python app.py
# http://localhost:5000
```

## Notes

- This is a demo: there is **no real security** (PINs are not hashed, the login
  is a single lookup). Don't expose real candidate data publicly until it's
  hardened.
- If login fails, the login page shows the technical error to make Railway/Odoo
  configuration issues easy to diagnose.
- Field names default to your database's Studio fields; override them with the
  optional variables if they ever change.
