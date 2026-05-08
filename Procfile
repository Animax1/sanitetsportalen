release: python manage.py migrate --noinput && python manage.py createcachetable && python manage.py collectstatic --noinput
web: gunicorn myproject.wsgi --workers ${WEB_WORKERS:-1} --threads ${WEB_THREADS:-4} --max-requests ${WEB_MAX_REQUESTS:-1000} --max-requests-jitter 50 --bind 0.0.0.0:$PORT --timeout 60
