from django.core.management.base import BaseCommand
from apps.products.pricing_engine import update_product_ai_prices, train_pricing_model

class Command(BaseCommand):
    help = 'Update AI-optimized prices for all products'

    def add_arguments(self, parser):
        parser.add_argument('--train', action='store_true', help='Retrain pricing model first')

    def handle(self, *args, **options):
        if options['train']:
            self.stdout.write('Training pricing model...')
            train_pricing_model()
            self.stdout.write(self.style.SUCCESS('Model trained!'))
        self.stdout.write('Updating AI prices...')
        count = update_product_ai_prices()
        self.stdout.write(self.style.SUCCESS(f'✅ Updated prices for {count} products'))
