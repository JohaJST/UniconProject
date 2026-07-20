from django.shortcuts import render

def about(request):
    return render(request, "about.html")

def self(request):
    return render(request, "self.html")

def self_check(request):
    return render(request, "self_check.html")
