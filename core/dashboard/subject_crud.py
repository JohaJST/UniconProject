from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg
from core.models import Subject, Test, ClassRoomsSubjects

def view_subject(request, pk):
    # Получаем предмет
    subject = get_object_or_404(Subject, pk=pk)
    
    # Классы, привязанные к этому предмету (без N+1)
    classrooms = ClassRoomsSubjects.objects.filter(
        subject=subject
    ).select_related('classroom')
    
    # Тесты предмета с подсчетом вопросов
    tests = Test.objects.filter(subject=subject).annotate(
        question_count=Count('variantas__questions', distinct=True)
    ).order_by('-created')
    
    # Агрегация среднего балла по всем результатам тестов этого предмета
    # Примечание: предполагается, что RelatedManager для Result называется result_set
    avg_score = Test.objects.filter(subject=subject).aggregate(
        avg=Avg('result__foyiz') 
    )['avg']
    
    return render(request, 'pages/dashboard/subject_detail.html', {
        'subject': subject,
        'classrooms': classrooms,
        'tests': tests,
        'avg_score': avg_score,
    })