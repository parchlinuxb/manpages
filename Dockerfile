FROM archlinux:base

RUN pacman -Syu --noconfirm && \
    pacman -S --needed --noconfirm \
    git \
    mandoc \
    pyalpm \
    python-chardet \
    python-django \
    python-django-csp \
    python-psycopg2 \
    python-requests \
    gunicorn && \
    pacman -Scc --noconfirm

WORKDIR /app

COPY . /app/

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
