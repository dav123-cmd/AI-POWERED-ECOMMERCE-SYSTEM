from django.core.management.base import BaseCommand
from apps.payments.fraud_detector import train_fraud_detector

class Command(BaseCommand):
    help = 'Train the PyTorch fraud detection autoencoder'

    def add_arguments(self, parser):
        parser.add_argument('--epochs', type=int, default=80)

    def handle(self, *args, **options):
        self.stdout.write('Training fraud detection model...')
        model = train_fraud_detector(epochs=options['epochs'])
        if model:
            self.stdout.write(self.style.SUCCESS('✅ Fraud model trained and saved!'))
        else:
            self.stdout.write(self.style.WARNING('⚠️  Training failed.'))
