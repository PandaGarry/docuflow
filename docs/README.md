# Документация семейной студии

## Актуальный production-переход · 2026-11-03

Читать в таком порядке:

1. [33 · План реализации](33-PRODUCTION-PLAN.md): что есть, что ещё предстоит,
   этапы, ресурсы и контрольные сцены.
2. [34 · Архитектура движка](34-ENGINE-ARCHITECTURE.md): кандидаты технологий,
   границы модулей, контракты и миграция.
3. [35 · Шлюзы качества](35-QUALITY-GATES.md): технические допуски,
   художественная приёмка и что является доказательством.
4. [36 · Живой чек-лист](36-PRODUCTION-TRACKER.md): задачи, зависимости,
   результаты и blockers. Генерируется из JSON, не редактируется вручную.
5. [37 · Решения и журнал](37-DECISION-LOG.md): причины выбора и отчёты итераций.
6. [38 · Blender MVP](38-BLENDER-MVP.md): исполнимый технический срез,
   команды запуска, происхождение runtime, доказательства и границы.
7. [39 · Внешние пакеты и bounded workers](39-EXTERNAL-PACKAGES-AND-BOUNDED-WORKERS.md):
   импорт модели/рига, resource budget, chunk-resume и блокинг папы.
8. [40 · Body-прототип и contact probes](40-BODY-RIG-AND-CONTACT-PROBES.md):
   IK ног, пальцы, цельная одежда и измерения evaluated geometry.
9. [41 · Деформации и visual review r3](41-DEFORMATION-REVIEW-R3.md):
   связные кисти, elbow helpers, 17 poses/72 кадра, сравнение и открытые art-дефекты.
10. [42 · Look-development r4](42-LOOKDEV-REVIEW-R4.md):
    пять новых native кадров, самопроверка внешности и обнаруженная регрессия сгибания кисти.
11. [43 · Исправление thumb-web regression r5](43-THUMB-WEB-REGRESSION.md):
    локализация, отклонённый эксперимент, исправление весов и новые крупные планы.

12. [44 · Rain v3 → мама: native appearance study](44-RAIN-MOM-STUDY.md):
    официальный .blend, реальные before/after, изменения skin/body/face, paired
    expression diagnostics и отдельная отрицательная художественная оценка.

13. [45 · Rain: сходство лица и обрамление A3–A5](45-RAIN-FACE-A3.md):
    нос/губы/челюсть, long parted hair на настоящем Rain, rejected A4 shading,
    actual reference/A2/A5 board и отдельный visual review без art approval.

14. [46 · Rain A6/A7: локальная фотосверка, мультяшный стиль](46-RAIN-PHOTO-GUIDED-A6.md):
    privacy boundary, лицо/палитра/crown/temple fixes, actual native before/after;
    личные фотографии не публикуются, exact likeness/art approval не заявляются.

15. [47 · Мама: A7 отклонён, primary-form reset](47-MOM-FORM-RESET.md):
    broad rejection, high-res eye-aligned диагностика, ошибки метода, отдельный
    native clay audit; следующий art milestone — новая голова, не новый отчёт.

Канонический источник состояния — [plan.json](../studio/production/plan.json).
[Первоначальный снимок окружения](../studio/production/environment.json) сделан
до установки изолированного runtime и не равен smoke test; [результаты проверки планового пакета](../studio/production/verification.json)
не равны приёмке полноценной анимации.

### Как вести документацию

```bash
# После изменения статуса/результата в JSON:
python3 studio/tools/production_status.py validate
python3 studio/tools/production_status.py checklist --write
python3 studio/tools/production_status.py checklist --check
python3 -m unittest discover -s studio/tests -p test_production_status.py -v

# Новый inventory snapshot — не headless render test:
python3 studio/tools/production_status.py doctor
```

Результат итерации записывается в 37: задача, revision, проверочная команда,
фактический результат, evidence, ограничения и следующий шаг. Новое одобрение
пользователя хранится отдельной записью с revision; не считается данным по
умолчанию. Проверки tracker запускаются в `.github/workflows/production-plan.yml`.
Контрактные тесты нового MVP — отдельный `.github/workflows/pipeline-contracts.yml`;
команда: `.cache/blender-venv/bin/python -m unittest discover -s studio/tests -p test_pipeline.py -v`.
Ни один из этих двух workflows не является Blender render smoke test.
Отдельный `rain-study.yml` действительно запускает pinned native bpy/Cycles,
публикует PNG и хранит редактируемый экспериментальный .blend как artifact;
его success тоже не является художественной/анимационной приёмкой.

## Исторические планы и технические материалы

- [00 · Vision](00-VISION.md), [03 · Character bible](03-CHARACTER-BIBLE.md),
  [13 · Стиль B](13-STYLE-B.md), [29 · Canon](29-CANON.md) — источники
  художественных требований; противоречия снимаются в ART-01, а не случайным
  смешиванием разных версий.
- [01 · Старый стек](01-STACK.md), [02 · Старый pipeline](02-PIPELINE.md),
  [08 · Старый roadmap](08-ROADMAP.md), [24 · Предыдущий план](24-PLAN.md) —
  исторические решения. Их сроки, статусы и будущие команды не являются
  подтверждением текущей реализации.
- [16 · Core](16-CORE.md), [21 · Экспериментальный 3D-риг](21-RIG.md),
  [23 · 2,5D](23-2P5D.md), [27 · Лицевые слои](27-FACE.md),
  [28 · Анимация](28-ANIM.md), [30 · Движение](30-MOTION.md) — опыт реализации.
- [25 · Наличие библиотеки](25-PROGRESS.md) — число файлов, не готовность
  трёх production-ригов. Наличие 115/115 рисунков не означает приёмку походки.
- [26 · Исторический журнал](26-LOG.md) — прежние попытки и ограничения.
- [31 · Предыдущий пилот](31-PILOT-LETTER-P.md),
  [32 · Предыдущая ревизия](32-CLEANUP-AND-ACTING.md) — контекст прошлых итераций.
  Наличие описания MP4 не гарантирует присутствие бинарника в текущей копии;
  это отдельно фиксируется doctor.
