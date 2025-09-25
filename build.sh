set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py migrate --noinput


if [[$CREATE_SUPERUSER]]; 
then
    python manage.py createsuperuser --no-input  --username $DJANGO_SUPERUSER_USERNAME --email $DJANGO_SUPERUSER_EMAIL
fi