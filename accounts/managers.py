"""Tilpasset bruker-manager for CustomUser."""
from django.contrib.auth.base_user import BaseUserManager


class CustomUserManager(BaseUserManager):
    """Manager for CustomUser – bruker username som identifikator."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        """Opprett og lagre en vanlig bruker.

        E-post er valgfri. Tom streng lagres som NULL slik at den betingede
        unique-constrainten på modellen fungerer korrekt.
        """
        if not username:
            raise ValueError('Brukernavn er påkrevd')
        email = self.normalize_email(email) if email else None
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """Opprett og lagre en superbruker."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        # NB: ingen setdefault på must_change_password. Modellens default er
        # True, og det er riktig også for superbrukere (S2): create_superuser
        # brukes kun av `create_admin` og `manage.py createsuperuser`, som begge
        # er bootstrapping der passordet kommer fra en miljøvariabel eller en
        # kommandolinje. Tvungent bytte ved første innlogging er nøyaktig det
        # man vil ha der.

        if not extra_fields.get('is_staff'):
            raise ValueError('Superbruker må ha is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superbruker må ha is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)
