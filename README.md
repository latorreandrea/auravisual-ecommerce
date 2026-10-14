# AuraVisual Ecommerce

> Django e-commerce project for AuraVisual physical products and customer customizations.

**AuraVisual Ecommerce** is the companion commerce platform for [aura-visual](https://github.com/latorreandrea/aura-visual), focused on selling and managing physical products such as customizable NFC cards and QR stands.

The core goal is to let customers personalize the products before purchasing them (for example front/back card graphics), preview the result, and complete checkout with account-aware order tracking.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Objectives](#objectives)
- [Core Features](#core-features)
- [Architecture](#architecture)
  - [Apps](#apps)
  - [Technology Stack](#technology-stack)
- [Setup & Installation](#setup--installation)
- [Environment Configuration](#environment-configuration)
- [Usage](#usage)
- [Authentication](#authentication)
- [Cart and Orders](#cart-and-orders)
- [Frontend Structure](#frontend-structure)
- [API Roadmap (Django Ninja + Stripe)](#api-roadmap-django-ninja--stripe)
- [Testing & Validation](#testing--validation)
- [Roadmap](#roadmap)
- [License](#license)

---

## Project Overview

AuraVisual Ecommerce extends the AuraVisual ecosystem with product catalog, stock, customization and purchasing workflows.

Current product focus:
- NFC PVC cards
- QR display stands

Customers can:
- register/login/logout,
- browse products,
- add/remove items from cart,
- attach customizations to base products,
- store shipping data,
- track order status.

---

## Objectives

- Provide a clean and scalable Django architecture for AuraVisual commerce.
- Keep UX/UI style consistent with `aura-visual` (base layout, navbar/footer, Bootstrap style baseline).
- Support customer accounts and order history.
- Prepare API best practices for future Stripe integrations.

---

## Core Features

- **Home app** for index and entry pages.
- **Products app** for base products and stock handling.
- **Accounts app** for profile, shipping data and order history.
- **Customizzations app** for customer visual customization workflows.
- **Cart app** for cart management and global cart context.
- **Orders app** for checkout domain and order state management:
  - `Order received`
  - `Being prepared`
  - `Shipped`
- **Toast notifications** for success and error feedback across the site.

---

## Architecture

### Apps

- `home`: landing/index views.
- `products`: product model, listing, stock info.
- `accounts`: user profile and shipping address domain.
- `customizzations`: user-to-product customization entities.
- `cart`: cart logic, add/remove/clear actions, global context processor.
- `orders`: order model and user order list.

### Technology Stack

- **Backend**: Python (WSL local), Django 5.2.x
- **Auth**: django-allauth
- **Frontend**: Django Templates + Bootstrap + shared style baseline from `aura-visual`
- **DB (default)**: SQLite (local dev baseline)

---

## Setup & Installation

```bash
cd /home/torre93/projects
git clone https://github.com/latorreandrea/auravisual-ecommerce.git
cd auravisual-ecommerce

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver   # DEBUG=True by default, static files are served
```

---

## Environment Configuration

Configuration uses `os.environ` in `settings.py`.

**Local development is the default.** `DEBUG` is ON unless `DEVELOPMENT` is set
to an explicit falsy value:

| `DEVELOPMENT` | `DEBUG` | Email backend |
| --- | --- | --- |
| unset | `True` | console |
| `1`, `true`, any other value | `True` | console |
| `0`, `false`, `no`, `off` | `False` | SMTP |

`DEBUG` and the email backend are both derived from that single flag
(`DEVELOPMENT = os.environ.get("DEVELOPMENT", "1").strip().lower() not in {"0", "false", "no", "off"}`),
so they can never disagree.

Production mode (`DEVELOPMENT=0`):
- `DEBUG=False`
- SMTP email settings from environment:
  - `EMAIL_PORT`
  - `EMAIL_HOST`
  - `EMAIL_HOST_USER`
  - `EMAIL_HOST_PASS`

Always available:
- `SECRET_KEY` (optional, has an insecure local-dev default)
- `ALLOWED_HOSTS` (optional, defaults to `127.0.0.1,localhost`)
- `ASSET_VERSION` (optional, defaults to `1`): cache-busting token appended to
  `css/style.css` and `js/main.js` in the templates

Example:

```bash
# local development (default: no variable needed, DEBUG=True)
python manage.py runserver

# production-like run
export DEVELOPMENT=0
python manage.py runserver
```

### Static files not loading?

`runserver` serves `/static/` and `/media/` **only while `DEBUG` is `True`**:
`django.contrib.staticfiles` wraps the handler with `StaticFilesHandler` when
`settings.DEBUG or --insecure` is true. A 404 on `css/style.css`, `js/main.js`,
`img/*` or even on `/static/admin/css/base.css` therefore almost always means the
server was started with `DEVELOPMENT=0`.

Fixes, in order of preference:

- make sure `DEVELOPMENT` is unset (or `1`) and `DEBUG` reports `True`:

  ```bash
  python manage.py shell -c "from django.conf import settings; print(settings.DEBUG)"
  ```

- if you must keep `DEBUG=False`, start the server with
  `python manage.py runserver --insecure`.

`collectstatic` is **not** needed for local development: the staticfiles finders
map `static/` directly. It is required only for a `DEBUG=False` deployment, where
files are collected into `STATIC_ROOT` (`staticfiles/`) and served by a dedicated
static server (WhiteNoise, nginx, CDN) — `runserver` never serves them in that
mode.

---

## Usage

1. Create an admin user:
   ```bash
   python manage.py createsuperuser
   ```
2. Add products from admin.
3. Access:
   - `/` home
   - `/shop/` product list
   - `/accounts/login/` authentication pages
   - `/cart/` cart details
   - `/orders/` user order list

---

## Authentication

Authentication is handled with **django-allauth**.

Custom templates are owned by the local `accounts` app:

- `accounts/templates/account/login.html`
- `accounts/templates/account/signup.html`
- `accounts/templates/account/logout.html`
- `accounts/templates/account/password_change.html`
- `accounts/templates/accounts/partials/auth_card.html` (shared heading block)

Template lookup walks `INSTALLED_APPS` in order, so the local apps are declared
**before** the `allauth` apps in `settings.py`: this is what makes the files
above shadow allauth's own `account/*.html` defaults.

Supported flows:
- registration
- login/logout
- password change

---

## Cart and Orders

- Session cart powers add/remove/clear actions.
- A cart context processor exposes cart summary globally for templates.
- Success toast includes a scrollable cart preview when cart items exist.
- Error toast displays failure reason (e.g. stock not available).

---

## Frontend Structure

The look and feel is shared 1:1 with the `aura-visual` project so the two sites
stay visually aligned.

- `static/css/style.css`: verbatim copy of the `aura-visual` baseline stylesheet
  followed by an **Ecommerce-only additions** section at the end of the file.
  Re-syncing from upstream keeps everything above that banner untouched.
- `static/js/main.js`: shared behaviour (fixed header state on scroll, mobile
  navigation toggle, dropdown expansion on mobile, section scroll-spy).
- `templates/base.html`: SEO/Open Graph meta blocks, JSON-LD structured data,
  Bootstrap + Bootstrap Icons + Google Fonts, and a `{% block extra_css %}` /
  `{% block extra_js %}` extension point.
- Cache busting: assets are requested as `{% static 'css/style.css' %}?v={{ ASSET_VERSION }}`
  where `ASSET_VERSION` comes from `auravisual_ecommerce/context.py`.

**AOS is intentionally not used.** The scroll animations of the baseline only
apply to content sections, while the navbar, footer and inner pages of this
project rely on plain CSS transitions and `main.js`. Keeping AOS out avoids a
third-party dependency that would not animate anything here.

### Template layout

Templates follow the Django convention of one namespaced
`<app>/templates/<app_name>/` directory per app, so every app ships and owns
its own markup:

| App | Templates |
| --- | --- |
| `home` | `home/templates/home/index.html` |
| `products` | `products/templates/products/list.html` |
| `cart` | `cart/templates/cart/detail.html` |
| `orders` | `orders/templates/orders/list.html` |
| `customizzations` | `customizzations/templates/customizzations/list.html` |
| `accounts` | `accounts/templates/accounts/*.html` and `accounts/templates/account/*.html` |

The `templates/` directory at the project root only holds what belongs to no
single app: `base.html` and the shared partials. `APP_DIRS` is enabled, so app
templates are discovered automatically without extra `DIRS` entries.

The logical name of a template (`products/list.html`, `account/login.html`) is
what views and `{% extends %}` / `{% include %}` statements use, so a template
can move between the project directory and its app without touching any Python
code.

Reusable partials:

- `templates/partials/navbar.html`: `aura-visual` header markup. It accepts an
  optional `header_class` (this project passes `header-solid`, because pages do
  not start with a dark hero section) and marks the active link with
  `request.resolver_match.app_name`. Home and Shop stay text links; the cart is
  an icon-only link whose item count is displayed as a floating badge (hidden
  when the cart is empty). Signed-out visitors get a single person icon that
  opens a Bootstrap dropdown with a compact sign-in form posting to
  `account_login`, plus a "Sign up" shortcut to `account_signup`.
- `templates/partials/footer.html`: `aura-visual` footer markup with the animated
  wave SVG, three columns (call to action, link groups, testimonial + social)
  and the `.btn-get-started` call to action.
- `accounts/templates/accounts/partials/auth_card.html`: heading block shared by
  the account pages (`title` required, `subtitle` optional).

Shared style building blocks used by the inner pages:

- `.section-title` for page headings with the green underline;
- `.info-card` + `.icon-wrap` for product, address, order and customization cards;
- `.btn-get-started` for primary actions and `.product-meta` / `.product-price`
  for catalogue details.

Navbar links: Home and Shop are text links, the cart is an icon with an item
count badge, and the account area collapses into a single panel icon. When
signed in the panel is not used and Profile, Orders, Customizations and Logout
stay in the navbar; when signed out the panel opens the email/username sign-in
form with the "Sign up" link underneath.

---

## API Roadmap (Django Ninja + Stripe)

Django Ninja is planned for API exposure and Stripe integration.

Recommended best practices for the next step:
- keep API in dedicated app (e.g. `api/`) with versioned routers (`/api/v1/...`);
- validate all payloads via Ninja schemas (Pydantic-based contracts);
- use idempotency keys for payment intents and webhooks;
- verify Stripe signatures server-side for each webhook;
- isolate payment service layer from view/router code;
- map payment lifecycle to order state transitions in a deterministic way;
- log request IDs, payment intent IDs and order IDs for traceability;
- implement retry-safe webhook handlers (at-least-once delivery model).

---

## Testing & Validation

Baseline checks:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py check
```

Optional:

```bash
python manage.py test
```

---

## Roadmap

- Add Django Ninja API app and payment endpoints.
- Integrate Stripe checkout and webhook pipeline.
- Add product customization preview rendering pipeline.
- Add shipment tracking integration.

---

## License

MIT (see [LICENSE](./LICENSE)).
