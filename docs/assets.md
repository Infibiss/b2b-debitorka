# Визуальные материалы

Hero: `web/public/hero.webp` (1672×941, локальный WebP, около 209 КБ). Создан встроенным ImageGen, 24.10.2026; затем сохранён в проект. Это редакционный образ реального сектора, не фотография офиса Mandato или клиента. Фирменный знак Mandato — локальный SVG; интерфейсные иконки — Lucide, шрифт — Manrope. Лицензии сторонних материалов включены в `web/public/third-party-notices.txt`.

Изображение сохранено для экрана входа; новая публичная главная использует интерфейсный сценарий без фоновой фотографии.

Полный использованный prompt:

> Use case: photorealistic-natural. Asset type: premium B2B finance product website hero background, wide landscape 16:9. Create an architectural editorial photograph: huge elegant modern white industrial warehouse / distribution center seen from elevated oblique aerial angle, quiet loading bays and long parallel shadows, pale warm concrete foreground, deep olive green forest and rolling fields at the far horizon, low morning sun. The scene should communicate the real economy, calm confidence, goods moving through businesses. Beautiful restrained art direction like a high-end architecture magazine, natural film grain, muted dark olive and warm grey palette, no saturated colors. Composition: architecture occupies lower right half; upper left has dark forest and muted sky with clean negative space for a large white website headline. Realistic, cinematic, exceptionally sophisticated. No text, logos, signs, people closeups, currency symbols, UI, watermarks or gradients.

## Экраны кабинета на главной

`web/public/product/debtors.jpg`, `case.jpg`, `portfolio.jpg` — снимки работающего локального кабинета Mandato, 24.11.2026, 1440×1000. Показывают реестр должников, независимые дела по договорам и обзор портфеля. Создан отдельный кабинет с вымышленными организациями и финансовыми записями; клиентские документы, персональные данные и ключи в изображения не включены. Интерфейс не дорисовывался. Общий вес трёх JPEG — около 260 КБ; изображения загружаются по мере приближения к экрану.

Оптимизация 24.11.2026: для карусели добавлены варианты320/720px в WebP (5–19КБ каждый), выбираемые через srcset. `hero-optimized.webp` — сжатая копия исходного hero, около110КБ; оригинал сохранён.
