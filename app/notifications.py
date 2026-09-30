"""Category messages are stored for retrieval; nothing is sent externally."""
from datetime import datetime, timezone

from .models import Notification


def category_for(total_cents: int):
    if total_cents < 10000:
        return 'LOW'
    return 'PREMIUM' if total_cents >= 1000000 else 'STANDARD'


def message_templates(category: str, marketing_enabled: bool):
    messages = []
    if category == 'LOW':
        messages.append(dict(kind='LOW_BALANCE_ALERT', templateId='low-balance-v1',
                             message='Your combined account balance is below 100.00.'))
        if marketing_enabled:
            messages.append(dict(kind='LOW_BALANCE_MARKETING', templateId='loan-options-v1',
                                 message='Explore available loan options and learn how to apply. Eligibility and approval depend on assessment.'))
    elif category == 'PREMIUM' and marketing_enabled:
        messages.append(dict(kind='PREMIUM_MARKETING', templateId='premium-v1',
                             message='Your combined balance has reached 10,000.00. Explore available premium banking benefits.'))
    return messages


class NotificationRepository:
    def __init__(self, database):
        self.collection = database.notifications

    def add_messages(self, customer_id, version, messages, transaction_id, session, category='LOW'):
        for message in messages:
            self.collection.insert_one(dict(customerId=customer_id, categoryVersion=version,
                                             category=category, transactionId=transaction_id,
                                             createdAt=datetime.now(timezone.utc), **message), session=session)

    def list_for_customer(self, customer_id, kind=None, offset=0, limit=50):
        query = {'customerId':customer_id}
        if kind:
            query['kind'] = kind
        return [Notification(notification_id=str(row['_id']), customer_id=str(row['customerId']),
                             category_version=row['categoryVersion'], category=row['category'],
                             kind=row['kind'], template_id=row['templateId'], message=row['message'],
                             transaction_id=str(row['transactionId']) if row['transactionId'] else None,
                             created_at=row['createdAt'])
                for row in self.collection.find(query).sort([('createdAt',-1),('_id',-1)]).skip(offset).limit(limit)]
