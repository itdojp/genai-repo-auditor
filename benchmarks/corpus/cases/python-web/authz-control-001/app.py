"""Synthetic negative control with an explicit tenant authorization predicate."""


def select_invoice(records, requested_id, actor_tenant):
    return next(
        (
            row
            for row in records
            if row["id"] == requested_id and row["tenant_id"] == actor_tenant
        ),
        None,
    )
