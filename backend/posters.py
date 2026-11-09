"""Small, server-side Cloudinary integration. No credentials reach templates."""
import io
import uuid
import warnings
from pathlib import Path

import cloudinary.uploader
from cloudinary.exceptions import Error
from flask import abort, current_app
from PIL import Image, UnidentifiedImageError


def _credentials():
    config = current_app.config
    return {key: config['CLOUDINARY_' + key.upper()] for key in ('cloud_name', 'api_key', 'api_secret')}


def upload(file):
    credentials = _credentials()
    data = file.stream.read(current_app.config['POSTER_MAX_BYTES'] + 1)
    if len(data) > current_app.config['POSTER_MAX_BYTES']:
        abort(400)
    formats = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}
    extension = Path(file.filename).suffix.lower()
    if extension not in formats:
        abort(400)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != formats[extension] or image.width * image.height > 25_000_000:
                    abort(400)
                image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        abort(400)
    stream = io.BytesIO(data)
    stream.name = 'poster' + extension
    result = cloudinary.uploader.upload(
        stream, **credentials, resource_type='image',
        public_id='roh/posters/' + uuid.uuid4().hex,
        overwrite=False, allowed_formats=['jpg', 'png', 'webp'], timeout=30,
    )
    return result['secure_url'], result['public_id']


def delete(public_id):
    if not public_id:
        return True
    try:
        result = cloudinary.uploader.destroy(public_id, **_credentials(), resource_type='image', invalidate=True, timeout=30)
        if result.get('result') in ('ok', 'not found'):
            return True
    except (Error, OSError, ValueError):
        pass
    # Cloudinary and SQL cannot share a transaction. Keep the saved event valid
    # and record the orphan's ID so an operator can retry deletion.
    current_app.logger.error('Cloudinary cleanup needs retry: public_id=%s', public_id)
    return False
