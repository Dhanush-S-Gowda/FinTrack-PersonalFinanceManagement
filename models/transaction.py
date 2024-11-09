from extensions import db
from datetime import datetime

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'category': self.category,
            'amount': self.amount,
            'description': self.description,
            'date': self.date.strftime('%Y-%m-%d'),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

    @staticmethod
    def get_monthly_summary(user_id):
        return db.session.query(
            db.func.strftime('%Y-%m', Transaction.date).label('month'),
            db.func.sum(Transaction.amount).label('total')
        ).filter_by(user_id=user_id).group_by('month').all()

    @staticmethod
    def get_category_summary(user_id, transaction_type):
        return db.session.query(
            Transaction.category,
            db.func.sum(Transaction.amount).label('total')
        ).filter_by(
            user_id=user_id,
            type=transaction_type
        ).group_by(Transaction.category).all()

    @staticmethod
    def get_total_by_type(user_id, type):
        return db.session.query(db.func.sum(Transaction.amount))\
            .filter_by(user_id=user_id, type=type)\
            .scalar() or 0.0