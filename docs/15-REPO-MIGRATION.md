# 15 · Переезд в репозиторий `family_studio`

## Состояние на сегодня

| Что | Результат |
|-----|-----------|
| `PandaGarry/family_studio` существует | ✅ да, публичный |
| Чтение через API (аккаунт) | ✅ работает (`gh api repos/... --jq .permissions` → `push:true`) |
| Запись через приложение/токен git | ❌ `403 Permission to PandaGarry/family_studio.git denied` |
| Содержимое целевого репозитория | 1 коммит, только авто-README — перезаписывать безопасно |
| История студии **без личных фото** | ✅ проверено (`studio/tools/migrate_repo.sh --dry-run`) |

То есть код и документация готовы к переносу, блокирует только одно: **права
записи у того приложения/токена, которым пушит git**. Права аккаунта в API
(`admin/push`) не заменяют прав приложения — Git-транспорт и REST-запись ходят
через разные авторизации.

## Как выдать права (пошагово)

### Что именно сломано — по факту замера

Приложение, которым я хожу в GitHub: **`arena-ai-coding-agent`** (установка на ваш
аккаунт). Проверка двух репозиториев одним и тем же токеном:

| Проверка | `docuflow` | `family_studio` |
|---|---|---|
| `POST /repos/<repo>/git/blobs` (нужен Contents: write) | ✅ `sha` вернулся | ❌ `403 Resource not accessible by integration` |
| `git push` | ✅ | ❌ `403 Permission ... denied` |
| `GET /repos/<repo>` (чтение) | ✅ | ✅ |

Вывод: **дело не в правах вашего аккаунта** (в API у вас `admin/push`) и не в
видимости репозитория, а в том, что токен выписан/установка ограничена
конкретным репозиторием сессии. Поэтому починка — не «настройки репозитория», а
привязка **Arena ↔ репозиторий** + права приложения.

### Шаг 1. В Arena: подключить репозиторий к сессии (главный шаг)

1. Настройки/подключения → **GitHub** → **Manage / Repository access**.
2. Включить `family_studio` (и оставить `docuflow`), сохранить.
3. Если пункта с репозиториями нет: **Disconnect GitHub → Connect GitHub** и в
   окне установки выбрать **Only select repositories** → `PandaGarry/family_studio`
   (и `PandaGarry/docuflow`).
4. После изменения доступа **начать новую сессию/чат** — токен выписывается при
   старте, в уже открытой сессии он останется старым.

### Шаг 2. На GitHub: проверить права приложения

1. Откройте `https://github.com/settings/installations`.
2. У `arena-ai-coding-agent` → **Configure**.
3. **Repository access**: `All repositories` *или* `Only select repositories` →
   добавить `family_studio` → **Save**.
4. **Permissions** (если раздел доступен): `Contents: Read and write`,
   `Metadata: Read`, `Pull requests: Read and write`.
5. Если GitHub показывает **«Review permission request»** — подтвердить.

### Шаг 3. Если пушите сами, своим токеном

Fine-grained token (рекомендуется):
`Settings → Developer settings → Personal access tokens → Fine-grained tokens →
Generate new token`

* **Repository access** → `Only select repositories` → `family_studio`
* **Permissions**: `Contents: Read and write`, `Metadata: Read`,
  `Pull requests: Read and write` (и `Workflows: Read and write`, если когда-то
  будем пушить `.github/workflows/`)
* Срок — минимальный разумный (30–90 дней)

Classic token (быстрее, но шире по правам): scope **`repo`**.

⚠️ Токен **не** нужно присылать в чат: он нужен только вашей локальной git-сессии.
Я работаю с тем, что настроено в песочнице, и пароли/токены не запрашиваю.

### Шаг 4. Проверка за 30 секунд

```bash
# 1) есть ли запись у приложения (вернётся sha — значит есть)
gh api -X POST repos/PandaGarry/family_studio/git/blobs -f content=probe -f encoding=utf-8

# 2) пускает ли git-транспорт (ничего не отправит)
git push --dry-run https://github.com/PandaGarry/family_studio.git HEAD:refs/heads/probe

# 3) кто вообще авторизован
gh auth status
```

Если (1) даёт `sha`, а (2) — `403`, значит `gh` и `git` ходят разными токенами:
смотреть `git config --get credential.helper` и `git credential fill`.

### Шаг 5. Защита ветки `main` (частая причина отказа после выдачи прав)

Переезд делает `push --force` (история переписывается, чтобы в ней не осталось
личных фото). Если на `main` включена защита:

`Settings → Branches → Branch protection rules` → правило для `main` →
либо снять правило на время переезда, либо включить **Allow force pushes**
(для владельца). После переезда защиту можно вернуть.

Если форсить `main` не хочется — скажите, и я сделаю переезд **без** force:
пуш в отдельную ветку `migration/privacy` + PR, который вы смержите сами.

## Перенос одной командой

```bash
# проверка: собрать историю без личных фото и убедиться, что их нет
bash studio/tools/migrate_repo.sh --dry-run

# перенос: force-push ветки студии в main целевого репозитория
bash studio/tools/migrate_repo.sh
# или с параметрами
BRANCH=arena/303d70d8-docuflow DST_URL=git@github.com:PandaGarry/family_studio.git \
  bash studio/tools/migrate_repo.sh
```

Скрипт делает ровно четыре вещи и ничего больше:

1. клонирует текущий репозиторий в `--mirror` (локально, во временную папку);
2. **переписывает историю**, вычищая `studio/reference/*.{webp,jpeg,jpg,png}`
   из **всех** коммитов (не только из последнего) через `git filter-branch`;
3. удаляет `refs/original`, чистит reflog и `gc` — старые коммиты с фото не
   остаются в клоне, который куда-то поедет;
4. **проверяет**, что в истории не осталось ни одного снимка, и только потом
   пушит (`--force`) в `main` целевого репозитория.

Если прав нет — скрипт падает с подсказкой, что именно проверить, и ничего не
отправляет. `--dry-run` делает всё, кроме push.

## Почему именно так, а не «удалить файлы коммитом»

Удаление файла новым коммитом не убирает его из истории: любой, кто клонирует
репозиторий, получает снимки из прошлых коммитов. Личные фото семьи — это не
то, что должно лежать в публичной истории, поэтому история переписывается.

Что уже сделано в текущем репозитории:

- `git rm --cached studio/reference/*` — файлы убраны из индекса;
- `.gitignore` → `studio/reference/*` (кроме `README.md`);
- `studio/reference/README.md` — правило: фото лежат **локально**, в git не
  попадают; если нужны для генерации — кладутся вручную и не коммитятся;
- `docs/11-LICENSING.md` — раздел про приватность;
- `studio/tools/migrate_repo.sh` — переписывание истории для переезда.

## Что переносится, а что нет

| Переносится | Не переносится |
|-------------|----------------|
| `docs/`, `studio/engine`, `studio/library`, `studio/characters` (JSON + мастера) | `studio/reference/*.webp\|jpeg` — личные фото (история чистится) |
| `studio/out/*.mp4`, контакт-листы, QA-отчёт (доказательства работы) | `studio/out/*.wav`, временные кадры — пересобираются, в `.gitignore` |
| `studio/fonts`, `studio/tools` | `.venv`, кеши |

## Чек-лист после переезда

- [ ] `main` целевого репозитория = история без фото (`git log --all --name-only | grep reference` → только README)
- [ ] `origin` указывает на `family_studio` (или на него переключена рабочая копия)
- [ ] ветка сессии запушена, PR открыт в целевом репозитории, старый PR закрыт
- [ ] README обновлён: имя проекта, ссылки на артефакты
- [ ] `studio/tools/migrate_repo.sh` больше не нужен — либо остаётся как инструмент на будущее

## Если решите остаться здесь

Тоже рабочий вариант: **Settings → Repository name → `family_studio`**.
GitHub перенаправит старые ссылки, структура внутри от имени не зависит.
Минус: история публичного репозитория остаётся прежней — фото придётся
вычищать тем же `migrate_repo.sh` (force-push в этот же репозиторий).
