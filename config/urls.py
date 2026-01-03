"""URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path

from limpa import views

urlpatterns = [
    path("", views.home, name="home"),
    path("podcasts/add/", views.add_podcast, name="add_podcast"),  # ty: ignore[no-matching-overload]
    path(
        "podcasts/<int:podcast_id>/delete/", views.delete_podcast, name="delete_podcast"
    ),  # ty: ignore[no-matching-overload]  # noqa: E501
    path("feed/<str:url_hash>/", views.serve_feed, name="serve_feed"),  # ty: ignore[no-matching-overload]
    path("podcasts/<int:podcast_id>/stats/", views.podcast_stats, name="podcast_stats"),  # ty: ignore[no-matching-overload]
    path("admin/", admin.site.urls),
]
