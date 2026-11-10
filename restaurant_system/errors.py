"""Error pages must survive unavailable database/context processors."""
from django.http import HttpResponse
from django.template.loader import render_to_string


def page_not_found(request, exception):
    response = HttpResponse(render_to_string('404.html'), status=404)
    response['X-Robots-Tag'] = 'noindex, nofollow, nosnippet'
    return response
