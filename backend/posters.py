"""Small, server-side Cloudinary integration. No credentials reach templates."""
import io
import uuid
import warnings
from pathlib import Path

import cloudinary.uploader
from cloudinary.exceptions import Error
from flask import current_app
from PIL import Image, UnidentifiedImageError


class PosterServiceError(Exception):
    pass


def _credentials():
    config = current_app.config
    values = {key: config['CLOUDINARY_' + key.upper()] for key in ('cloud_name', 'api_key', 'api_secret')}
    if not all(values.values()):
        raise PosterServiceError('Poster uploads are unavailable. Please contact an administrator.')
    return values


def upload(file):
    credentials = _credentials()
    data = file.stream.read(current_app.config['POSTER_MAX_BYTES'] + 1)
    if len(data) > current_app.config['POSTER_MAX_BYTES']:
        raise ValueError('Posters must be at most 5 MB.')
    formats = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}
    extension = Path(file.filename).suffix.lower()
    if extension not in formats:
        raise ValueError('Choose a JPEG, PNG, or WebP poster.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != formats[extension] or image.width * image.height > 25_000_000:
                    raise ValueError('Choose a valid JPEG, PNG, or WebP image under 25 megapixels.')
                image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('The poster could not be read as an image.') from None
    stream = io.BytesIO(data)
    stream.name = 'poster' + extension
    try:
        result = cloudinary.uploader.upload(
            stream, **credentials, resource_type='image',
            public_id='roh/posters/' + uuid.uuid4().hex,
            overwrite=False, allowed_formats=['jpg', 'png', 'webp'], timeout=30,
        )
    except (Error, OSError):
        raise PosterServiceError('The poster upload failed. Your event has not been changed; please try again.') from None
    return result['secure_url'], result['public_id']


def delete(public_id):
    if not public_id:
        return True
    try:
        result = cloudinary.uploader.destroy(public_id, **_credentials(), resource_type='image', invalidate=True, timeout=30)
        if result.get('result') in ('ok', 'not found'):
            return True
    except (Error, OSError, PosterServiceError):
        pass
    # Cloudinary and SQL cannot share a transaction. Keep the saved event valid
    # and record the orphan's ID so an operator can retry deletion.
    current_app.logger.error('Cloudinary cleanup needs retry: public_id=%s', public_id)
    return False
