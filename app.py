"""
ConfiaRH — customer portal (demo)

A small read-only dashboard. Customers log in with the email + PIN stored on
their res.partner record, then see the hr.job records linked to them and the
hr.applicant records behind each job.

Everything talks to Odoo through the external XML-RPC API using read methods
only (search_read / fields_get). The app never creates, writes or deletes
anything in Odoo.

All configuration comes from environment variables (set them on Railway).
"""

import os
import xmlrpc.client
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, session
)

# ---------------------------------------------------------------------------
# Configuration (Railway -> Variables)
# ---------------------------------------------------------------------------
ODOO_URL = os.environ.get("ODOO_URL", "").rstrip("/")   # e.g. https://confiarh.odoo.com
ODOO_DB = os.environ.get("ODOO_DB", "")                 # database name
ODOO_USERNAME = os.environ.get("ODOO_USERNAME", "")     # API user login (an email)
ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "")       # API key for that user

# Studio field names. Defaults match your database; override via env if needed.
PARTNER_PIN_FIELD = os.environ.get("PARTNER_PIN_FIELD", "x_studio_pin")
JOB_PARTNER_FIELD = os.environ.get(
    "JOB_PARTNER_FIELD", "x_studio_many2one_field_5j_1jrv1qb8f"
)

# Session signing key. Fine to leave as-is for the demo.
SECRET_KEY = os.environ.get("SECRET_KEY", "confiarh-demo-not-secret")

app = Flask(__name__)
app.secret_key = SECRET_KEY


# ---------------------------------------------------------------------------
# Minimal read-only Odoo client
# ---------------------------------------------------------------------------
class OdooReadOnly:
    """Thin wrapper around Odoo's external API. Exposes read methods only."""

    def __init__(self, url, db, username, api_key):
        self.url = url
        self.db = db
        self.username = username
        self.api_key = api_key
        self._uid = None
        self._fields_cache = {}
        self.common = xmlrpc.client.ServerProxy(
            f"{url}/xmlrpc/2/common", allow_none=True
        )
        self.models = xmlrpc.client.ServerProxy(
            f"{url}/xmlrpc/2/object", allow_none=True
        )

    @property
    def uid(self):
        if self._uid is None:
            self._uid = self.common.authenticate(
                self.db, self.username, self.api_key, {}
            )
            if not self._uid:
                raise RuntimeError(
                    "Odoo authentication failed. Check ODOO_URL, ODOO_DB, "
                    "ODOO_USERNAME and ODOO_API_KEY."
                )
        return self._uid

    def _execute(self, model, method, args, kwargs=None):
        return self.models.execute_kw(
            self.db, self.uid, self.api_key, model, method, args, kwargs or {}
        )

    def search_read(self, model, domain, fields=None, limit=None, order=None):
        kwargs = {}
        if fields is not None:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if order is not None:
            kwargs["order"] = order
        return self._execute(model, "search_read", [domain], kwargs)

    def available_fields(self, model):
        if model not in self._fields_cache:
            fg = self._execute(model, "fields_get", [], {"attributes": ["type"]})
            self._fields_cache[model] = set(fg.keys())
        return self._fields_cache[model]

    def pick_fields(self, model, desired):
        """Keep only the requested fields that actually exist on the model.

        Studio configs differ between databases, so this avoids crashes when a
        field we ask for isn't present.
        """
        available = self.available_fields(model)
        return [f for f in desired if f in available]


_odoo_singleton = None


def get_odoo():
    """One shared client per worker (caches the login + field metadata)."""
    global _odoo_singleton
    if _odoo_singleton is None:
        _odoo_singleton = OdooReadOnly(
            ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY
        )
    return _odoo_singleton


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
def rel_label(value):
    """A many2one comes back from Odoo as [id, "Name"] or False."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[1]
    return ""


def rel_id(value):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0]
    return None


def short_date(value):
    """'2026-06-25 09:30:00' -> '25/06/2026'."""
    if not value or not isinstance(value, str):
        return ""
    date_part = value.split(" ")[0]
    try:
        y, m, d = date_part.split("-")
        return f"{d}/{m}/{y}"
    except ValueError:
        return date_part


app.jinja_env.filters["rel_label"] = rel_label
app.jinja_env.filters["short_date"] = short_date


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "partner_id" not in session:
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    if "partner_id" in session:
        return redirect(url_for("jobs"))
    return render_template("login.html", error=None)


@app.route("/login", methods=["POST"])
def login():
    email = (request.form.get("email") or "").strip()
    pin_raw = (request.form.get("pin") or "").strip()

    if not email or not pin_raw:
        return render_template(
            "login.html",
            error="Veuillez saisir votre email et votre code PIN.",
        )

    try:
        pin_value = int(pin_raw)
    except ValueError:
        return render_template(
            "login.html",
            error="Identifiants incorrects. Vérifiez votre email et votre code PIN.",
        )

    try:
        odoo = get_odoo()
        fields = odoo.pick_fields(
            "res.partner", ["name", "email", "commercial_partner_id"]
        )
        domain = [
            ("email", "=ilike", email),
            (PARTNER_PIN_FIELD, "=", pin_value),
        ]
        partners = odoo.search_read("res.partner", domain, fields, limit=1)
    except Exception as exc:
        # Demo: surface the technical reason so config issues are easy to spot.
        return render_template(
            "login.html",
            error="Connexion au système impossible pour le moment.",
            debug=str(exc),
        )

    if not partners:
        return render_template(
            "login.html",
            error="Identifiants incorrects. Vérifiez votre email et votre code PIN.",
        )

    partner = partners[0]
    session.clear()
    session["partner_id"] = partner["id"]
    session["partner_name"] = partner.get("name") or email
    commercial = rel_id(partner.get("commercial_partner_id"))
    session["commercial_partner_id"] = commercial or partner["id"]
    return redirect(url_for("jobs"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/jobs")
@login_required
def jobs():
    partner_id = session["partner_id"]
    commercial_id = session.get("commercial_partner_id", partner_id)

    odoo = get_odoo()
    desired = [
        "name", "department_id", "address_id", "contract_type_id",
        "no_of_recruitment", "application_count", "is_published",
    ]
    fields = odoo.pick_fields("hr.job", desired)

    # Match the job's customer field against the logged-in partner OR its parent
    # company, so it works whether the field points to the contact or the company.
    domain = [
        "|",
        (JOB_PARTNER_FIELD, "=", partner_id),
        (JOB_PARTNER_FIELD, "=", commercial_id),
    ]
    job_list = odoo.search_read("hr.job", domain, fields, order="name asc")

    return render_template(
        "jobs.html",
        jobs=job_list,
        company=session.get("partner_name", ""),
        has_count="application_count" in fields,
    )


@app.route("/jobs/<int:job_id>/applicants")
@login_required
def applicants(job_id):
    partner_id = session["partner_id"]
    commercial_id = session.get("commercial_partner_id", partner_id)
    odoo = get_odoo()

    # Re-check the job belongs to this customer before showing candidates.
    job_fields = odoo.pick_fields("hr.job", ["name", "department_id", "address_id"])
    job_domain = [
        "&",
        ("id", "=", job_id),
        "|",
        (JOB_PARTNER_FIELD, "=", partner_id),
        (JOB_PARTNER_FIELD, "=", commercial_id),
    ]
    job_rows = odoo.search_read("hr.job", job_domain, job_fields, limit=1)
    if not job_rows:
        return render_template(
            "applicants.html", job=None, applicants=[],
            company=session.get("partner_name", ""),
        )
    job = job_rows[0]

    app_desired = [
        "partner_name", "email_from", "partner_phone", "partner_mobile",
        "stage_id", "kanban_state", "create_date",
    ]
    app_fields = odoo.pick_fields("hr.applicant", app_desired)
    app_rows = odoo.search_read(
        "hr.applicant",
        [("job_id", "=", job_id)],
        app_fields,
        order="create_date desc",
    )
    return render_template(
        "applicants.html",
        job=job,
        applicants=app_rows,
        company=session.get("partner_name", ""),
    )


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
