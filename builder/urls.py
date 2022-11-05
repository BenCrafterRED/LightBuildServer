from django.urls import path

from . import views

app_name = 'builder'
urlpatterns = [
    path('triggerbuild/<str:user>/<str:project>/<str:package>/<str:branchname>/<str:distro>/<str:release>/<str:arch>', views.buildtarget, name='triggerbuild'),
    path('cancelplannedbuild/<str:user>/<str:project>/<str:package>/<str:branchname>/<str:distro>/<str:release>/<str:arch>', views.cancelbuild, name='cancelplannedbuild'),
]
