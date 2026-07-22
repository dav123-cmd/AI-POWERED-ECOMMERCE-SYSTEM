from django.core.management.base import BaseCommand
from apps.analytics.forecasting import train_forecast_model, save_forecasts

class Command(BaseCommand):
    help = 'Train LSTM sales forecasting model and generate forecasts'

    def add_arguments(self, parser):
        parser.add_argument('--epochs',  type=int, default=100)
        parser.add_argument('--days',    type=int, default=14, help='Days to forecast ahead')
        parser.add_argument('--no-save', action='store_true',  help='Train only, do not save forecasts')

    def handle(self, *args, **options):
        self.stdout.write('Training LSTM forecast model...')
        model = train_forecast_model(epochs=options['epochs'])
        if model:
            self.stdout.write(self.style.SUCCESS('✅ Model trained!'))
            if not options['no_save']:
                save_forecasts(options['days'])
                self.stdout.write(self.style.SUCCESS(f'✅ Saved {options["days"]}-day forecast'))
        else:
            self.stdout.write(self.style.WARNING('⚠️  Training failed.'))
