from django.conf.urls import url
from cl.visualizations.views import (
    delete_visualization,
    edit_visualization,
    mapper_homepage,
    new_visualization,
    restore_visualization,
    view_embedded_visualization,
    view_visualization,
)

urlpatterns = [
    url(
        r'^visualizations/scotus-mapper/$',
        mapper_homepage,
        name='mapper_homepage',
    ),
    url(
        r'^visualizations/scotus-mapper/new/$',
        new_visualization,
        name='new_visualization',
    ),
    url(
        r'^visualizations/scotus-mapper/(?P<pk>\d*)/edit/$',
        edit_visualization,
        name='edit_visualization',
    ),
    url(
        # Check JS files if changing this config.
        r'^visualizations/scotus-mapper/delete/$',
        delete_visualization,
        name='delete_visualization',
    ),
    url(
        r'^visualizations/scotus-mapper/restore/',
        restore_visualization,
        name='restore_visualization',
    ),
    url(
        r'^visualizations/scotus-mapper/(?P<pk>\d*)/embed/$',
        view_embedded_visualization,
        name='view_embedded_visualization',
    ),
    url(
        r'^visualizations/scotus-mapper/(?P<pk>\d*)/(?P<slug>[^/]*)/$',
        view_visualization,
        name='view_visualization',
    ),
]
