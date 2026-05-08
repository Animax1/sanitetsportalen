#!/usr/bin/env python
"""Django management utility for pasientregistreringssystemet."""
import os
import sys


def main():
    """Kjør administrative oppgaver."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Klarte ikke å importere Django. Er det installert og aktivert i "
            "virtuelt miljø?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
