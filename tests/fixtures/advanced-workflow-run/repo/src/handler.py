def handle_upload(request):
    token = request.headers.get("X-Fixture-Token")
    return render_report(request.body, token)
