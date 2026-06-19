"""
BillingCycle — finds due subscriptions, generates invoices, posts ledger DEBITs,
advances the subscription period. Must be IDEMPOTENT (safe to run twice).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from operator import sub
from typing import Callable, Optional, Self

from billing_engine.db import (
    Database,
    CustomerRepository, PlanRepository, SubscriptionRepository,
    UsageRecordRepository, InvoiceRepository, InvoiceLineItemRepository,
    LedgerRepository,
)
from billing_engine.models import Subscription
from billing_engine_starter.billing_engine.models import customer
from billing_engine_starter.billing_engine.models.invoice import Invoice
from billing_engine_starter.billing_engine.models.ledger import LedgerEntry
from datetime import timedelta

from billing_engine.billing.pipeline import build_invoice
from billing_engine.models import (
    InvoiceStatus,
    LedgerEntry,
    LedgerDirection,
    SubscriptionStatus,
)

@dataclass
class BillingResult:
    invoices_created: int
    invoices_skipped_duplicate: int
    trials_activated: int


class BillingCycle:
    """Day-3 deliverable. Day-4 stretch: add `upgrade_subscription(...)`."""

    def __init__(
        self,
        db: Database,
        customer_repo: CustomerRepository,
        plan_repo: PlanRepository,
        subscription_repo: SubscriptionRepository,
        usage_repo: UsageRecordRepository,
        invoice_repo: InvoiceRepository,
        line_item_repo: InvoiceLineItemRepository,
        ledger_repo: LedgerRepository,
        strategy_factory: Callable,    # given a Plan, returns a PricingStrategy
        discount_factory: Callable,    # given a discount_id or None, returns a Discount or None
        tax_factory: Callable,         # given a Customer, returns (TaxCalculator, TaxContext)
    ) -> None:
        self.db = db
        self.customer_repo = customer_repo
        self.plan_repo = plan_repo
        self.subscription_repo = subscription_repo
        self.usage_repo = usage_repo
        self.invoice_repo = invoice_repo
        self.line_item_repo = line_item_repo
        self.ledger_repo = ledger_repo
        self.strategy_factory = strategy_factory
        self.discount_factory = discount_factory
        self.tax_factory = tax_factory

    # --------------------------------------------------------
    def run(self, as_of: date) -> BillingResult:

     invoices_created = 0
     invoices_skipped_duplicate = 0
     trials_activated = 0

    # activate trials
     for sub in self.subscription_repo.list_all():

        if (
             sub.status == SubscriptionStatus.TRIAL
             and sub.trial_end
             and sub.trial_end < as_of
        ):
            self.subscription_repo.update_status(
                sub.id,
                SubscriptionStatus.ACTIVE,
            )

            trials_activated += 1

     due_subscriptions = self.subscription_repo.get_due_for_billing(
        as_of
    )

     for sub in due_subscriptions:

        if (
            self.invoice_repo.count_for_subscription(
                sub.id
            )
            > 0
        ):
            invoices_skipped_duplicate += 1
            continue

        customer = self.customer_repo.get(
            sub.customer_id
        )

        plan = self.plan_repo.get(
            sub.plan_id
        )

        strategy = self.strategy_factory(plan)

        discount = self.discount_factory(
            sub.discount_id
        )

        tax_calc, tax_context = self.tax_factory(
            customer
        )

        usage_quantity = self.usage_repo.sum_for_period(
            sub.id,
            "calls",
            sub.current_period_start,
            sub.current_period_end,
        )

     invoice = build_invoice(
            subscription=sub,
            plan=plan,
            strategy=strategy,
            discount=discount,
            tax_calc=tax_calc,
            tax_context=tax_context,
            usage_quantity=usage_quantity,
            period_start=sub.current_period_start,
            period_end=sub.current_period_end,
            invoice_count_so_far=self.invoice_repo.count_for_subscription(
                sub.id
            ),
        )

     invoice.status = InvoiceStatus.ISSUED

    invoice =Self.invoice_repo.add(
            Invoice
        )

    for item in invoice.line_items:

            Self.line_item_repo.add(
                item.__class__(
                    id=None,
                    invoice_id=invoice.id,
                    description=item.description,
                    amount=item.amount,
                    kind=item.kind,
                )
            )

    Self.ledger_repo.add(
            LedgerEntry(
                id=None,
                invoice_id=invoice.id,
                customer_id=customer.id,
                amount=invoice.total,
                direction=LedgerDirection.DEBIT,
                reason=f"Invoice {invoice.id}",
            )
        )

    Self.subscription_repo.update_period(
            sub.id,
            sub.current_period_end,
            sub.current_period_end + timedelta(days=28),
        )

 

    # --------------------------------------------------------
    def upgrade_subscription(self, subscription_id: int, new_plan_id: int, switch_date: date) -> None:
        """Mid-cycle upgrade — Day 4 stretch."""
        # TODO Day 4
        raise NotImplementedError("Day 4: implement BillingCycle.upgrade_subscription")
