Подготовка и сборка APK (Windows с Android Studio / Gradle)

1) Требования на машине сборки:
- JDK 17 (Temurin/Adoptium или OpenJDK 17)
- Android SDK + платформы для `compileSdk 33`
- Android Studio (opcional) или Gradle в PATH

2) Что добавлено в проект:
- `gradlew` и `gradlew.bat` — placeholder-скрипты в `android/`.
- `gradle/wrapper/gradle-wrapper.properties` — указывает на Gradle 8.4.
- `app/keystore.properties.template` — шаблон для подписи релизов.

3) Генерация/дополнение wrapper (если `gradle-wrapper.jar` отсутствует):
- Откройте Android Studio и импортируйте проект `android` — студия сгенерирует wrapper.
- Или на машине с Gradle (и JDK 17) выполните в `android`:
  ```powershell
  gradle wrapper --gradle-version 8.4 --distribution-type all
  ```

4) Сборка APK (Debug):
  ```powershell
  cd C:\path\to\repo\android
  .\gradlew.bat clean assembleDebug
  ```
  Результат: `android\app\build\outputs\apk\debug\`

5) Сборка Release (подписанный):
- Создайте `app/keystore.properties` на основе шаблона и настройте `signingConfigs` в `app/build.gradle`.
- Затем:
  ```powershell
  .\gradlew.bat clean assembleRelease
  ```

Если на сервере возникнут ошибки — пришлите лог, я помогу их исправить.
