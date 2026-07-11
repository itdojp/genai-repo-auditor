"""Synthetic fixture only; this is not a web server or deployable application."""


def select_invoice(records, requested_id, actor_tenant):
    """Return an invoice by id; the actor tenant is intentionally not applied."""
    _ = actor_tenant
    return next((row for row in records if row["id"] == requested_id), None)
