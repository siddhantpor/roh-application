import datetime

def format_date(date):
    if not date: 
        return date
    try:
        day = datetime.date.fromisoformat(str(date)[:10])
    except ValueError:
        return date
    return day.strftime('%m-%d-%Y')

def format_time(time):
    if not time:
        return time
    try:
        parsed = datetime.time.fromisoformat(str(time))
    except ValueError:
        return time
    return parsed.strftime('%I:%M %p').lstrip('0')

def init(app):
    app.add_template_filter(format_date, 'format_date')
    app.add_template_filter(format_time, 'format_time')
