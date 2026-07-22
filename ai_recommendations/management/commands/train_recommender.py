from django.core.management.base import BaseCommand
from apps.ai_recommendations.recommender import train_recommender

class Command(BaseCommand):
    help = 'Train the AI recommendation model'

    def add_arguments(self, parser):
        parser.add_argument('--epochs', type=int, default=30)
        parser.add_argument('--batch-size', type=int, default=512)
        parser.add_argument('--min-interactions', type=int, default=50)

    def handle(self, *args, **options):
        self.stdout.write('Training recommendation model...')
        model = train_recommender(
            epochs=options['epochs'],
            batch_size=options['batch_size'],
            min_interactions=options['min_interactions'],
        )
        if model:
            self.stdout.write(self.style.SUCCESS('✅ Model trained and saved!'))
        else:
            self.stdout.write(self.style.WARNING('⚠️  Insufficient data to train.'))
