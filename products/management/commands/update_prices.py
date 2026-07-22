from django.core.management.base import BaseCommand
from apps.products.pricing_engine import train_pricing_model, batch_update_prices

class Command(BaseCommand):
    help = 'Train and apply AI dynamic pricing to all products'

    def add_arguments(self, parser):
        parser.add_argument('--train',     action='store_true', help='Retrain pricing model first')
        parser.add_argument('--dry-run',   action='store_true', help='Show changes without saving')
        parser.add_argument('--category',  type=str, default=None, help='Category slug to update')

    def handle(self, *args, **options):
        if options['train']:
            self.stdout.write('Training pricing model...')
            train_pricing_model()
            self.stdout.write(self.style.SUCCESS('✅ Model trained'))
        count = batch_update_prices(
            category_slug=options.get('category'),
            dry_run=options['dry_run']
        )
        action = 'Would update' if options['dry_run'] else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'💰 {action} {count} product prices'))
