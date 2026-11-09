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
- [Customization Workflow](#customization-workflow)
- [Cart, Checkout and Stock](#cart-checkout-and-stock)
- [Promotions](#promotions)
- [Staff tools](#staff-tools)
- [Product Catalogue Side Gallery](#product-catalogue-side-gallery)
- [Frontend Structure](#frontend-structure)
- [API Roadmap (Django Ninja + Stripe)](#api-roadmap-django-ninja--stripe)
- [Testing](#testing)
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
- **Products app** for base products and stock handling, including a staff
  three-step product creation wizard.
- **Accounts app** for profile, shipping data and order history.
- **Customization app** for customer visual customization workflows:
  - per-product sides (front/back) with an optional printable area each, managed
    in the staff product wizard or the admin: a side is either **customizable**
    (one print area, one customer image) or **fixed** (printed exactly as its
    mockup);
  - drag/resize/rotate editor with PNG, JPEG and WebP uploads, one image per side;
  - named, user-scoped projects with optimized WebP previews and cart integration;
  - one print ZIP per project, containing a print-resolution PNG per side (ready
    for CardPresso);
  - Vanilla-Tilt cards on the home page (up to 14° on the hero and 10° on the
    catalogue cards, with a deeper `translateZ` and no glare overlay so the card
    never detaches from its panel), plus a mobile gyroscope mode with a ±45°
    range. Workspace project cards tilt on their miniature image only, so the
    product name, project name and price below stay flat and readable.
- **Cart app** for cart management and global cart context.
- **Promotions app** for staff-defined quantity bundles on a single product:
  - a promotion has a name and a ladder of price breaks (e.g. 5 units for
    EUR 40, 10 units for EUR 70), managed from the Admin **or** from the staff
    pages at `/promotions/`;
  - a break covers its own units at the break price, while the units above it
    stay at the product base price: with a EUR 10 base price and the ladder
    above, 7 units cost EUR 60 (5 for EUR 40 + 2 × EUR 10) instead of EUR 70;
  - the cheapest break wins, inactive promotions are ignored everywhere, and
    every price comes from one shared pricing service, so the cart, the
    catalogue and the home page can never disagree.
- **Orders app** for checkout and order state management:
  - in-app checkout at `/orders/checkout/` (shipping address + order summary);
  - fulfilment states: `Order received`, `Being prepared`, `Shipped`;
  - payment states: `Awaiting payment`, `Paid`, `Payment failed`, `Refunded`;
  - stock states: `No stock taken`, `Stock reserved`, `Stock committed`,
    `Reservation released` (see [Cart, Checkout and Stock](#cart-checkout-and-stock)).
- **Staff tools** (`/staff/`) replacing the old navbar "Create product" link:
  two rows — read-only counters with the latest promotions, then one action card
  per area of the shop (products, promotions, orders, site admin) — plus the
  promotion manager, the product edit page and the staff shortcuts on `/shop/`.
- **Toast notifications** for success and error feedback across the site.

---

## Architecture

### Apps

- `home`: landing/index views and the staff hub at `/staff/`.
- `products`: product model, listing, stock info and the staff product pages.
- `promotions`: per-product quantity price breaks (staff-defined in the Admin or
  in `/promotions/`, read-only for the storefront).
- `accounts`: user profile and shipping address domain.
- `customization`: customization projects, previews, print archives and the editor.
- `cart`: cart logic, add/remove/clear actions, global context processor.
- `orders`: checkout, order model, stock bookkeeping and user order list.

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
  `css/style.css`, `js/main.js`, `css/product-wizard.css` and
  `js/product-wizard.js` in the templates

Pagination (`auravisual_ecommerce/pagination.py`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `PRODUCTS_PAGE_SIZE` | `12` | Products per page in `/shop/` |
| `PROJECTS_PAGE_SIZE` | `8` | Saved projects per page in `/customization/` |

Checkout:

| Variable | Default | Purpose |
| --- | --- | --- |
| `STOCK_RESERVATION_MINUTES` | `30` | How long a stock hold survives before `expire_stock_holds` releases it (used by the Stripe flow) |
| `STORE_CURRENCY` | `EUR` | ISO 4217 code stored on every order and sent to the payment provider |

Customization uploads and print output:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CUSTOMIZATION_MAX_UPLOAD_MB` | `10` | Hard per-image cap; each product side can only lower it |
| `CUSTOMIZATION_MAX_TOTAL_UPLOAD_MB` | `50` | Combined limit for one save request |
| `CUSTOMIZATION_MAX_IMAGE_PIXELS` | `40000000` | Rejects images whose display dimensions exceed this |
| `CUSTOMIZATION_PREVIEW_MAX_WIDTH` | `1200` | Maximum width of the rendered preview before encoding |
| `CUSTOMIZATION_PREVIEW_MAX_BYTES` | `102400` | Target maximum size of the generated WebP preview |
| `CUSTOMIZATION_PREVIEW_WEBP_QUALITY` | `80` | Starting WebP quality; reduced automatically if needed |
| `CUSTOMIZATION_PRINT_DPI` | `300` | DPI metadata written into the PNGs inside the print ZIP |
| `CUSTOMIZATION_PRINT_ASYNC` | `1` | Generate print files in a background thread |
| `CUSTOMIZATION_PRINT_WEBHOOK_SECRET` | empty | Shared secret for the order-paid webhook; empty disables it |

Example:

```bash
# load the variables of a local .env file into the current shell
# (the app never parses .env itself: it reads os.environ)
set -a; . ./.env; set +a

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
2. Sign in as a staff user and choose **Staff tools** in the navbar (or open
   `/staff/`), then **Create product**, or open `/shop/create/` directly. The
   three-step wizard creates the product and one or more product sides, each of
   which is either customizable or fixed:
   - **Step 1 – Product details:** title, description, base price, stock and
     catalogue visibility.
   - **Step 2 – Sides & print areas:** upload a mockup per side, preview it
     locally in the browser, then (for customizable sides) draw, move or resize
     the printable rectangle. Use **Use the entire side** when the whole
     optimized mockup may be customized, or switch
     **Customers can customize this side** off for a fixed side: the preview keeps
     showing the mockup (labelled **Mockup preview** / **Printed as-is**) so the
     admin can still check what will be printed.
     A product supports up to eight sides and needs at least one customizable
     side.
   - **Step 3 – Review:** confirm the details and each side's kind/area, then
     create everything in a single transaction.

   The mockup is optimized on the server and the drawn ratios are converted to
   pixels using the final optimized canvas dimensions. The Admin remains
   available for later maintenance.
3. Access:
   - `/` home (public)
   - `/shop/` product list (public)
   - `/shop/create/` three-step product wizard (staff only)
   - `/shop/<slug>/deactivate/` soft-delete a product (staff only, POST)
   - `/cart/` cart details (public)
   - `/accounts/login/` and `/accounts/signup/` authentication pages
   - `/orders/` user order list (authenticated)
   - `/customization/` saved customization projects (authenticated, own projects)
   - `/customization/product/<slug>/` customization editor (authenticated)
   - `/admin/` Django administration (staff only): products, sides, promotions
     and their price breaks

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

### Access control

| Area | Anonymous visitor | Registered customer | Staff / superuser |
| --- | --- | --- | --- |
| Home, products, cart | Yes | Yes | Yes |
| Customization editor and projects | Redirected to login with `next` | Own projects only | Own projects only in the storefront |
| Project detail, payload, delete | Redirected to login | Own projects only; others return `404` | Own projects only; others return `404` |
| `/admin/` | Login page | No access | Full admin access |
| `/shop/create/` | Redirected to login | `403 Forbidden` | Three-step product wizard |
| `/shop/<slug>/deactivate/` | Redirected to login | `403 Forbidden` | Deactivate (soft delete) product |
| Print webhook | Token-protected | Token-protected | Token-protected |

`LOGIN_URL` points to `account_login`, so every `@login_required` view redirects
anonymous users to `/accounts/login/?next=<original-url>`. The custom login and
signup templates render allauth's `{{ redirect_field }}` hidden input: without
it the `next` parameter would be lost after authentication.

When the redirect comes from a customization URL, the login page:

- uses the title **Sign in to customize**;
- shows a dedicated **Create a free account** call to action;
- preserves the same `next` URL on the signup link, so a new customer lands
  directly in the editor or project list after registration.

The navbar and footer only show **Customizations** to authenticated users and
**Staff tools** / **Admin** to staff users. Product catalogue and cart
customization buttons send anonymous visitors to the login page with the editor
URL already stored in `next`.

---

## Customization Workflow

1. Create the product with the staff wizard at `/shop/create/`, or manage the
   full set in admin. The wizard saves a product and one or more **product
   sides**. Each side carries at most one printable area, and that area is the
   side's only customization surface:
   - a **customizable side** has `print_x`, `print_y`, `print_width` and
     `print_height` in canvas pixels plus rotation/scaling rules and an optional
     lower upload cap;
   - a **fixed side** has no print dimensions: customers never see it in the
     editor and it is printed exactly as its mockup. In the wizard the mockup
     preview stays visible while the switch is off, with a **Preview only** banner
     over the stage, a **Fixed side** badge and an inline warning next to the
     switch; only the printable-area controls are hidden.

   `ProductView.is_customizable` is simply `bool(print_width and print_height)`,
   so there is no separate zone table to keep in sync.
   - The uploaded mockup is optimized to WebP first. The rectangle is drawn as
     ratios (`0..1`) in the browser and converted to pixels only after the
     optimized canvas dimensions are known, preventing offsets between the
     preview and the saved area.
   - **Use the entire side** stores `x=0`, `y=0`, `width=canvas_width_px` and
     `height=canvas_height_px`.
   - Side order is normalized to `1..n`; a product accepts from one to eight
     sides. The default area is centered with a 10% inset.
   - Staff can retire an existing product from the customization editor with
     **Deactivate product**. The action sets `is_active=False`, so the product
     disappears from the catalogue, editor, cart and project list while its
     sides, print areas, projects and uploaded files remain intact. Reactivate
     it from the Django admin, where `is_active` can be toggled inline in the
     product list.
2. A signed-in customer opens `/customization/product/<slug>/`. The editor only
   lists customizable sides, one file input each. Anonymous visitors are
   redirected to the login page, which invites them to create an account while
   preserving the editor URL in `next`. The browser editor checks the same
   format, per-image byte and pixel limits as the server before submitting, and
   the size/rotation sliders share their geometry with the server renderer.
3. Saving validates every transform, stores each upload under the project UUID,
   keeps the optional project name, renders a compressed WebP preview of the
   first customized side (by `sort_order`, capped at
   `CUSTOMIZATION_PREVIEW_MAX_WIDTH`, with its alpha channel preserved so a
   cut-out mockup stays transparent in the workspace and catalogue cards) and
   deletes assets that are no longer referenced. EXIF orientation is applied
   consistently by the browser and the server renderer; rotations are rendered
   with 2x supersampling plus a LANCZOS downscale. Only the print pipeline
   (`customization/services/printing.py`) flattens the artwork on white, because
   the printing service expects opaque PNGs.
4. Projects appear in `/customization/`, which is paginated
   (`PROJECTS_PAGE_SIZE` projects per page, newest first), and on the home page,
   where the hero shows the most recently updated project and the workspace lists
   the last eight as compact miniatures (product name, project name, price and
   last edit date). Each project can be added to the cart with `draft_id`; the
   cart line is keyed by `<product_id>:<draft_id>` so the same product can be
   ordered with different artwork.
5. When checkout reports a paid order, POST the draft IDs to
   `/customization/webhooks/order-paid/` with the shared secret in the
   `X-Webhook-Token` header:

   ```json
   {"draft_ids": ["<uuid>", "<uuid>"]}
   ```

   The endpoint queues print generation and answers `202`. Every project
   produces a single ZIP archive at `customization/prints/<uuid>.zip` that holds
   one print-resolution PNG per side, named after the side (`Front.png`,
   `Back.png`, with a numeric suffix on name collisions). Fixed sides are
   included as their mockup, while customizable sides without a customer image
   are skipped. Set `CUSTOMIZATION_PRINT_ASYNC=0` to render synchronously; the
   admin action **Generate print file** rebuilds the archive on demand.

All customization views require authentication. Every queryset is filtered by
`user=request.user`, so project detail, payload, delete and update endpoints are
owner-only; another customer's project returns `404`. Projects that belong to an
inactive product are hidden from `/customization/` and return `404` from the
detail and payload endpoints until the product is reactivated. The webhook is
the only machine-to-machine exception: it is CSRF-exempt but requires the
compared in constant time) and never redirects to the login
page.

---

## Cart, Checkout and Stock

- Session cart powers add/remove/clear actions.
- A cart context processor exposes cart summary globally for templates.
- Line prices come from the promotions pricing service, so quantity breaks are
  applied per line (see [Promotions](#promotions)).
- Success toast includes a scrollable cart preview when cart items exist.
- Error toast displays failure reason (e.g. stock not available).

### Checkout

`/cart/` links to `/orders/checkout/`, which asks for a shipping address
(prefilled from the last one; a fresh `ShippingAddress` row per order keeps the
history intact) and shows the same totals as the cart.
`orders.services.place_order()` then, inside one transaction:

1. locks the products with `select_for_update()` and checks
   `Product.available_quantity`;
2. prices every cart line with `promotions.services.price_line` and stores the
   total on the order (`total_amount`, `currency`);
3. creates the order cart (`Cart` + one `CartItem` per product, so the plain
   product and a customized line of the same product are merged);
4. reserves and commits the stock.

An empty cart, an unpublished product or a quantity above the free stock raises
`CheckoutError`: the transaction rolls back, no order is created, the stock is
untouched and the customer gets one readable message per problem. The cart page
and the checkout button already know about a shortfall
(`cart_summary.items[].available_quantity`, `exceeds_stock`,
`cart_summary.has_stock_issue`), so it is repaired before the payment step.

### Stock: reserve → commit → release

`Product.stock_quantity` is what sits on the shelf, `Product.reserved_quantity`
is what pending payments hold, and `Product.available_quantity`
(= `stock_quantity - reserved_quantity`) is the only number the shop sells. A
`CheckConstraint` keeps `reserved_quantity <= stock_quantity`.

| Step | Effect on the product | When |
| --- | --- | --- |
| `reserve_stock(order)` | `reserved_quantity += n`, sets `reserved_until` | Checkout, with a payment provider |
| `commit_stock(order)` | `reserved_quantity -= n`, `stock_quantity -= n` | Payment confirmed |
| `release_stock(order)` | `reserved_quantity -= n` | Payment failed, cancelled or hold expired |

The order records the step in `stock_state` (`none`, `reserved`, `committed`,
`released`) next to `payment_status` (`unpaid`, `paid`, `failed`, `refunded`).
Both functions are idempotent, so a webhook delivered twice cannot move the stock
twice.

There is no gateway yet, so `place_order` calls reserve **and** commit in the same
transaction: the shop behaves exactly like an immediate decrement. Every write is
an `F()` update guarded inside the `filter()`
(`stock_quantity__gte`, `reserved_quantity__lte=F("stock_quantity") - n`), so two
concurrent checkouts can never oversell: the loser updates zero rows and its
transaction rolls back.

Promotions never change the units: an order of 7 units takes 7 units off the
shelf and only changes the price (5 for EUR 40 + 2 at the base price).

### Ready for Stripe

Only the second call has to move when a provider is wired in:

1. `POST /orders/checkout/` reserves the units (`reserve_stock`), sets
   `payment_status=unpaid` and `stripe_payment_intent_id`, and redirects to the
   provider page — `place_order` will stop before `commit_stock`;
2. the signed webhook calls `commit_stock(order)` and sets
   `payment_status=paid`;
3. a failed/expired payment calls `release_stock(order)` and sets `failed`;
4. `python manage.py expire_stock_holds [--dry-run]` (cron or Celery beat) frees
   every hold older than `STOCK_RESERVATION_MINUTES` and marks the unpaid order
   `failed`.

Because the order snapshots `total_amount` and `currency`, the amount sent to
Stripe is the one the customer saw, even if a price or a promotion changed in
between.

---

## Promotions

Promotions are a staff-only feature: the Admin defines them and the storefront
only reads them. A `Promotion` belongs to **one** product and holds one or more
`PromotionTier` rows (quantity → total price), so a bundle never spreads across
products or cart lines.

### Price rule

A break covers its own units at the break price, and any unit above the break
keeps the product base price. The storefront always picks the eligible break with
the lowest net total and falls back to the base price when no break is cheaper.

With a EUR 10.00 base price and the ladder `5 for EUR 40` / `10 for EUR 70`:

| Quantity | Gross | Net | Saving | Break used |
| --- | --- | --- | --- | --- |
| 4 | EUR 40.00 | EUR 40.00 | EUR 0.00 | none |
| 7 | EUR 70.00 | EUR 60.00 (40 + 2 × 10) | EUR 10.00 | 5 for EUR 40 |
| 10 | EUR 100.00 | EUR 70.00 | EUR 30.00 | 10 for EUR 70 |
| 25 | EUR 250.00 | EUR 220.00 (70 + 15 × 10) | EUR 30.00 | 10 for EUR 70 |

Two cart lines of 4 units each are priced separately and never reach the
5-unit break.

### Admin validation

The ladder is validated as a whole (`Promotion.validate_tiers`, shared by the
Admin inline and by the staff pages through `promotions/forms.py`), so a
promotion cannot be saved when:

- it has no breaks, or two breaks for the same quantity (also a
  `UniqueConstraint` on `promotion` + `quantity`);
- a break is not a saving, i.e. `price >= base_price × quantity`;
- a total does not grow with the quantity, or a break does not lower the unit
  price of the previous one;
- a break price is not greater than zero (also a `CheckConstraint`).

`ProductAdmin` lists the promotions of a product as a read-only inline that
links to the promotion page, where the breaks are edited.

### Where the prices appear

- `/cart/`: struck-through gross line total, net total, "You save" per line and
  for the whole cart (`cart_summary.subtotal`, `discount_total`, `total`);
- `/shop/` and `/`: a badge with the best break on the product card
  (`T-shirt bundle: 10 for €70.00`), loaded with two queries per page;
- each cart line also exposes `unit_price`, `gross_line_total`, `line_total`,
  `discount_total`, `promotion_name`, `promotion_label` and `extra_units`.

`promotions/services.py` is the only place that computes a price:
`active_promotions_for()` (bulk `{product_id: [promotion]}` map with the breaks
prefetched), `price_line()` (one line, returns a `LinePricing` dataclass),
`best_break()` and `attach_promotion_badges()` (catalogue and home cards).

### Staff pages

`/promotions/` is the day-to-day manager, for staff only (`login_required` plus
an `is_staff` check, exactly like `products.views`):

| Route | What it does |
| --- | --- |
| `GET /promotions/` | every promotion with product, ladder, best unit price and status; `?q=` searches the promotion and product name, `?status=active\|inactive\|all` filters |
| `GET/POST /promotions/create/` | new promotion + ladder; `?product=<id>` prefills the product (used by the catalogue cards and the product edit page) |
| `GET/POST /promotions/<id>/` | edit the promotion and its breaks, see the saved ladder with the saving of each break, delete dialog |
| `POST /promotions/<id>/delete/` | deletes the promotion; the product goes back to its base price |

`promotions/forms.py` holds the shared pieces: `PromotionTierForm` (used by the
Admin inline), `PromotionTierFormSet` (the ladder validation, also used by the
Admin), `StaffPromotionTierForm` (the same break plus Bootstrap classes) and
`PromotionTierStoreFormSet` (`extra=1`, `can_delete=True`). The view validates the
promotion form first, because the ladder is compared against the product base
price of the *selected* product, then saves both in one transaction.

`static/js/promotion-formset.js` adds a break by cloning the `<template>` rendered
from `tier_formset.empty_form` and flags a saved break for deletion without
renumbering the remaining rows; emptying a fresh row is enough to ignore it, so
the page also works without JavaScript.

### Not implemented yet

Percentage discounts, coupon codes, cross-product or category promotions,
minimum-cart thresholds and validity windows (start/end dates). Promotions allow
one row per product: a second promotion for the same product is accepted by the
model but only the cheapest active one is used.

---

## Staff tools

`/staff/` is the staff hub and replaces the old navbar "Create product" shortcut:
the navbar pill, the footer link and the home hero now say **Staff tools** and
point here. The page is read-only and split in two rows:

- **Overview** (row 1): five counters — products, published, out of stock
  (`stock_quantity <= reserved_quantity`), active/total promotions and orders —
  plus the five most recently updated promotions. The counters that map to a page
  (products, promotions, orders) are their own shortcut;
- **Actions** (row 2): one card per area of the shop, each with the button(s) that
  own the data:
  - *Products* → `/shop/` (list, where the staff actions live) and `/shop/create/`;
  - *Promotions* → `/promotions/` and `/promotions/create/`;
  - *Orders* → the admin order changelist;
  - *Site admin* → the admin product changelist (mockups and printable areas) and
    the admin index.

The catalogue itself is the staff workspace, so the shortcuts live next to the
products they change (`/shop/`, signed in as staff):

- the card title links to `/shop/<slug>/edit/`;
- a toolbar per card: `stock_quantity` on the shelf plus the held units, **Edit**,
  **Promotion** (or **Add a promotion**, opening `/promotions/create/?product=<id>`
  with the product already filled) and **Hide** (POST to
  `/shop/<slug>/deactivate/`, shown only while the product is published);
- a **Show hidden products (N)** toggle switches the same page to the deactivated
  products (`?status=hidden`), where each card carries the **Hidden** badge, the
  edit/promotion actions and no customer call to action; **Show published
  products** goes back. Page links keep the filter, so paging through the hidden
  products works. Customers never see the toggle: `?status=` is ignored, so the
  hidden products stay invisible to them.

| Route | Page |
| --- | --- |
| `GET /staff/` | staff hub (`home:staff`) |
| `GET /shop/` | catalogue; staff toolbar, plus `?status=hidden` for the hidden products |
| `GET /shop/<slug>/edit/` | product edit (`products:edit`) |
| `GET /promotions/` · `/promotions/create/` · `/promotions/<id>/` | promotion manager |
| `GET /shop/create/` | three-step product wizard (unchanged) |
| `POST /shop/<slug>/deactivate/` | soft delete (unchanged); reactivate from the edit page |

The product edit page only touches the scalar fields (title, description, base
price, stock, visibility): mockups and printable areas still need the wizard or
the admin, because they must be checked visually. Saving sends the staff member
back to `/shop/`, and a hidden product shows the **Hidden** badge instead of the
"View product" link.

All staff pages share `static/css/staff.css`, are gated with `login_required` +
`is_staff` (a signed-in customer gets a 403, an anonymous visitor the login page)
and link back to the hub. The catalogue loads the same stylesheet only for staff
accounts, for the toolbar on the cards.

---

## Product Catalogue Side Gallery

Shop cards show the first product side as a preview and expose the other sides
through an integrated mini-gallery:

- the first side is server-rendered and remains visible without JavaScript;
- desktop hover advances the sides every 1.5 seconds in a continuous loop, then
  resets to the first side on `mouseleave`;
- previous/next arrows, dots, touch swiping and keyboard arrows/Home/End are
  available for manual control;
- autoplay pauses on keyboard focus, hidden tabs, touch devices and
  `prefers-reduced-motion`, and stays stopped after a manual action until the
  pointer leaves and re-enters the card;
- products with a single mockup render as a static image, while products without
  any mockup render an aligned placeholder.

Views are prefetched and ordered by `sort_order`, and only sides with a
`mockup_image` enter the gallery. Only the first gallery image is `eager`; all
remaining sides are `lazy`.

`/shop/` is paginated in SQL (`Paginator` + `PRODUCTS_PAGE_SIZE`, alphabetical by
title): only the products of the current page and their sides are loaded, plus
one `COUNT`. The pagination bar is a shared partial
(`templates/partials/pagination.html`) with previous/next links and `rel`
attributes; a missing, non-numeric, zero or out-of-range `?page=` falls back to
the first/last page instead of answering `404`. Every card on `/shop/` previews
the base product, never a customer's saved draft.

The home page shows the **latest six** active products (newest first) as a
teaser, plus a **Browse the full catalogue** button that leads to the paginated
`/shop/`.

---

## Frontend Structure

The look and feel is shared 1:1 with the `aura-visual` project so the two sites
stay visually aligned.

- `static/css/style.css`: verbatim copy of the `aura-visual` baseline stylesheet
  followed by an **Ecommerce-only additions** section at the end of the file.
  Re-syncing from upstream keeps everything above that banner untouched.
- `static/js/main.js`: shared behaviour (fixed header state on scroll, mobile
  navigation toggle, dropdown expansion on mobile, section scroll-spy).
- `static/js/product-wizard.js`: staff-only wizard behaviour (step navigation,
  local mockup previews, add/remove/reorder sides, the customizable/fixed side
  toggle, rectangle drawing, moving, resizing, keyboard controls, review
  rendering and AJAX submission).
- `static/js/customization-editor.js`: customer editor (one image per
  customizable side, drag, size and rotation sliders, project name and
  client-side validation before the JSON payload is posted).
- `static/js/card-tilt.js`: Vanilla-Tilt bootstrap for `[data-tilt]` cards
  (per-card `data-tilt-max`, `data-tilt-speed` and `data-tilt-scale` overrides,
  no glare overlay, gyroscope on mobile with a ±45° range, an on-demand
  permission button for iOS 13+ and no motion at all under
  `prefers-reduced-motion`).
- `static/js/product-gallery.js`: catalogue-card side gallery (clone-based
  looping, hover autoplay on fine pointers, arrows, dots, touch swipe, keyboard
  navigation/pausing and reduced-motion support).
- `static/css/product-wizard.css`: wizard layout, stepper, face tabs,
  checkerboard stage, printable rectangle and handles, review cards, responsive
  rules and reduced-motion support.
- `static/css/staff.css`: staff-only pages (`/staff/`, `/promotions/`,
  `/shop/<slug>/edit/`) and the staff toolbar on `/shop/` (loaded for staff
  accounts only): page header, stat cards, action cards, catalogue/tables, status
  badges, filters and the inline formset rows. Shipped as a separate file with
  the same palette as `style.css`, so the storefront never downloads it.
- `static/js/promotion-formset.js`: add/remove rows of the promotion ladder
  (clones `tier_formset.empty_form`, ticks the `DELETE` checkbox of a saved
  break, empties a fresh row so the formset ignores it).
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
| `home` | `home/templates/home/index.html` and `home/templates/home/staff_dashboard.html` |
| `products` | `products/templates/products/list.html`, `products/templates/products/create_product.html`, `products/templates/products/edit_product.html` and `products/templates/products/partials/face_form.html` |
| `promotions` | `promotions/templates/promotions/list.html`, `create.html`, `detail.html`, `_form.html` and `_tier_row.html` |
| `cart` | `cart/templates/cart/detail.html` |
| `orders` | `orders/templates/orders/list.html` and `orders/templates/orders/checkout.html` |
| `customization` | `customization/templates/customization/*.html` |
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
  `request.resolver_match.app_name`. The streamlined nav keeps Home and
  Products as text links, adds How it works / File guide section links and shows
  Customizations only to authenticated users plus a staff-only **Staff tools**
  shortcut (`/staff/`, styled with `.nav-staff-link`). The cart is an icon-only
  link whose item count is displayed as a
  floating badge (hidden when the cart is empty). The account icon always opens
  a Bootstrap dropdown: signed-out visitors get a compact sign-in form posting
  to `account_login` and a "Sign up" shortcut that preserves `next`; signed-in
  users get a profile summary with Profile, Orders, Customizations, Admin (staff
  only) and Logout.
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

Navbar links: Home and Products are text links, How it works and File guide jump
to the matching home sections, and the cart is an icon with an item count badge.
The account panel is the single place for Profile, Orders, Customizations,
Admin and Logout when signed in, or the email/username sign-in form plus the
"Sign up" link when signed out.

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

The order and stock models are already shaped for it (see
[Ready for Stripe](#ready-for-stripe)): a payment intent id field, a separate
`payment_status`, the `stock_state` cycle and a `total_amount`/`currency`
snapshot that must be sent to Stripe as the authoritative amount. The webhook
only has to call `commit_stock()` (paid), `release_stock()` (failed/refunded) and
set `payment_status`; it never touches prices.

---

## Testing

### Automated checks

Run the product-focused suite first, then the full project suite and deployment checks:

```bash
python manage.py test products
python manage.py test promotions
python manage.py test orders
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
```

Expected result: all tests pass, `check` reports no issues, no migrations are
generated, and `git diff --check` reports no whitespace errors. Tests use a
temporary `MEDIA_ROOT`, so no uploaded mockups are left in the project.

The product suite covers:

- anonymous redirects to login and `403` responses for authenticated non-staff
  users;
- the three-step wizard markup, management form and default single side;
- creating a single customizable side, or a product that mixes customizable and
  fixed sides (the fixed side stores no print dimensions);
- normalized side order and per-side canvas dimensions after WebP optimization;
- ratio-to-pixel conversion against the **optimized** canvas, including resized
  mockups and **Use the entire side** areas;
- rejection of missing sides, more than eight sides, out-of-bounds rectangles
  and missing mockups;
- persistence of advanced area settings, stock and catalogue visibility;
- the catalogue CTA disappearing when a product has no customizable side;
- structured AJAX validation errors (step, face and field names) without partial
  database writes, plus the successful JSON redirect response;
- the catalogue side gallery: ordered mockup-only views, prefetched relations,
  accessible arrows/dots, an eager first image, lazy remaining sides and the
  placeholder for products without mockups;
- catalogue pagination: `PRODUCTS_PAGE_SIZE` products per page in alphabetical
  order, inactive products excluded from both the page and the counter,
  `?page=` falling back on invalid, zero and out-of-range values, and no
  pagination markup when everything fits on one page;
- staff-only soft deletion: the POST flips `is_active`, hides the product from
  the catalogue and editor while preserving its sides, print areas and projects,
  treats a repeat request as idempotent and rejects anonymous, non-staff and
  non-POST requests;
- the staff product edit page (title, description, price, stock and visibility
  updated, invalid data leaving the stored product untouched, the promotion card
  linking to its promotion or to the prefilled create form, `403` for customers,
  login redirect for anonymous visitors and `404` for an unknown slug);
- `Product.available_quantity` (stock minus holds) and `is_out_of_stock`.

The `customization` suite covers upload limits and formats, EXIF orientation,
the single-image-per-side JSON payload, transform clamping inside the print
area, project save/rename/replace/delete asset cleanup, preview generation from
the first customized side, the alpha channel kept in the WebP preview while the
print PNGs stay flattened on white, cart integration, the ZIP archive (exact file
names and per-side PNG dimensions, fixed sides included), the paginated project
list (`PROJECTS_PAGE_SIZE`, out-of-range pages, no bar for a single page), webhook
authentication, anonymous login redirects, cross-user project isolation, the
staff-only deactivation action and the hiding of projects that belong to
inactive products.
The `home` suite covers the hero (latest project), the eight-project workspace of
compact miniatures (product name, project name, price, and the tilt hooks only on
the preview), the empty states, the latest-six catalogue teaser with its links to
the full catalogue, the base-product previews that never borrow a customer draft,
and the Vanilla-Tilt hooks (tilt angles, no glare overlay, no product-name bar in
the hero). The `accounts` and `cart` suites cover the signup/login `next` flow,
the customization signup invitation, staff-only admin access and the anonymous
customization CTAs.

The `promotions` suite covers the pricing rule (`price_line` for 4, 7, 10 and 25
units, the cheapest break winning between two promotions, units above a break
staying at the base price, inactive promotions ignored, promotions never crossing
products and cart lines priced one by one), the ladder validation (missing breaks,
a break that is not a saving, totals that do not grow, a unit price that does not
drop, the unique break per quantity and the positive price constraint), the cart
summary keys and the cart page ("You save", struck-through gross total), the
`/shop/` and `/` badges, the staff-only Admin pages (creating a promotion with its
breaks, rejecting an empty or non-saving ladder, the read-only inline on the
product page) and the query counts (three for the cart, two per catalogue page).
The staff pages are covered too: login redirects and `403` for customers, the
searchable/filterable list, creating a promotion with its ladder, the `?product=`
prefill, a non-saving and an empty ladder both rejected, editing one break while
deleting another, the delete modal and the POST-only delete.

The `orders` suite covers the checkout page (cart summary, prefilled address),
placing an order (total snapshot, `paid`/`committed`, stock decremented, cart
emptied), promotions changing the price but not the units (7 units → EUR 60, 3
left on the shelf), two cart lines of the same product merged into one `CartItem`,
insufficient stock rolling the whole checkout back (no order, no stock movement,
no orphan address), empty carts and unpublished products, the required shipping
address, the login redirect for anonymous visitors, the order history, and the
reserve/commit/release cycle: idempotent reserve and commit, `available_quantity`
dropping while a hold exists, a full hold blocking the last units, commit without
a hold, release giving the units back, and the `expire_stock_holds` command
(releasing expired holds, marking the unpaid order failed, `--dry-run` and holds
still inside their window).

The `home` suite also covers the staff hub: login redirect and `403`, the five
overview counters, the latest five promotions, the seven links of the four action
cards and the absence of any table or write action (those moved to `/shop/`). The
`products` suite covers the staff shortcuts on the catalogue: the edit/promotion/
hide actions and the held units (staff only), the hidden-products toggle
(`?status=hidden` for staff, ignored for customers and anonymous visitors), the
hidden badge and missing customer call to action, the page links keeping the
filter and a constant query count per page.

### Manual QA: product wizard

Use a staff account and open `/shop/create/`:

1. **Access and navigation**
   - Sign out and confirm the URL redirects to login with `next=/shop/create/`.
   - Sign in as a customer and confirm `403 Forbidden`.
   - Sign in as staff and confirm steps 1–3 render, only step 1 is visible, and
     the progress bar and stepper match the current step.
2. **Product details**
   - Submit empty required fields and confirm the wizard stays on step 1 and
     highlights the fields.
   - Enter a title, description, price, stock and visibility.
3. **Sides and print areas**
   - Upload a transparent PNG; confirm the preview appears immediately and the
     image was not uploaded before final submit (check the Network panel).
   - Draw a new rectangle, move it, resize it from all eight handles, and use
     the arrow keys plus `Shift` + arrow keys.
   - Change the numeric percentages and confirm the rectangle follows.
   - Enable **Use the entire side** and confirm the handles disappear; disable it
     and confirm the previous custom rectangle returns.
   - Switch **Customers can customize this side** off and confirm the mockup
     preview stays visible, the rectangle and the **Use the entire side** switch
     disappear, a **Preview only** banner and an inline warning explain that the
     side will be printed as uploaded, the badge reads **Fixed side** and the
     review says **Fixed side** / **Printed exactly as the mockup**.
   - Add sides, rename them, reorder them, and remove one. Confirm the
     **Add side** button disables at eight sides and the last side cannot be
     removed.
   - Submit without a mockup and confirm the active side is selected with a
     native validation message.
4. **Review and persistence**
   - Confirm the review shows the product values and every side with its preview
     and area summary.
   - Create the product and confirm the success toast and catalogue redirect.
   - In Admin, confirm each `ProductView` has the expected `sort_order`,
     `canvas_width_px` and `canvas_height_px`, and that customizable sides store
     `print_*` values that fit inside the optimized canvas while fixed sides keep
     them empty (the **Kind** column shows `Customizable` or `Fixed`).
   - Open the customer editor and confirm it only lists customizable sides and
     that the saved area lines up with the same mockup.
5. **Failure and fallback paths**
   - Submit an invalid or oversized mockup via AJAX and confirm the affected
     step/side is shown, errors are attached to the fields or area, and nothing
     is saved.
   - Disable JavaScript and confirm all three steps remain visible, the
     server-rendered side defaults to **Use the entire side**, and the form still
     submits normally.
   - Test at 375 px, 768 px and desktop widths, with keyboard-only navigation
     and `prefers-reduced-motion` enabled.

### Manual QA: customer flow, projects and home page

1. **Editor**
   - Open a product that mixes one fixed side and one customizable side; confirm
     only the customizable side appears in the tabs and the fixed side never
     offers an upload.
   - Upload an image, zoom to 150%, rotate it, switch sides and back: the
     placement must survive without leaving the print area.
   - Type a project name and save; the detail page and `/customization/` must show
     it, and the generated preview must show the first customized side only.
2. **Home page**
   - With at least one project, `/` shows **Your latest project** in the hero and
     up to eight compact project miniatures in the workspace (four per row on a
     desktop), each with the product name, the project name, the price and the
     last edit date.
   - Hover the hero and the catalogue cards: they tilt with the pointer (up to 14°
     on the hero, 10° on the catalogue cards, 12° on the miniatures) without any
     glare patch, so the lit area matches the card instead of its transparent
     padding. **Only the image** of a workspace card tilts: the caption below
     stays flat and readable. The hero shows the badge and the preview only, with
     no product-name bar. On a phone, tap **Tilt with your phone** (iOS) and
     confirm the cards follow the device; with `prefers-reduced-motion` enabled
     nothing moves.
   - Save a project on a mockup with a transparent background: the WebP preview
     keeps the cut-out (no white box) in the workspace card and on
     `/customization/`, while the PNG inside the print ZIP stays flattened on
     white.
   - Without projects the hero reads **Design it once. See it instantly.** and the
     workspace shows **No projects yet**.
3. **Catalogue and pagination**
   - Create more than `PRODUCTS_PAGE_SIZE` products (12 by default) and open
     `/shop/`: page 1 lists the first 12 titles alphabetically, the bar offers page
     2, `?page=999` lands on the last page and `?page=abc` (or `?page=0`) lands on
     the first one.
   - The home catalogue section shows the six newest products only, with **The
     catalogue** eyebrow and the **Full catalogue** / **Browse the full
     catalogue** links leading to `/shop/`.
   - Save more than `PROJECTS_PAGE_SIZE` projects (8 by default) and repeat the
     check on `/customization/`: newest first, one page at a time.
4. **Print archive**
   - Trigger `/customization/webhooks/order-paid/` (or the admin action
     **Generate print file**) and unzip the stored archive: one PNG per side,
     named after the side, at the mockup resolution.

### Manual QA: staff tools, promotions and checkout

1. **Staff hub (`/staff/`)**
   - Sign in as staff: the navbar pill reads **Staff tools** and opens `/staff/`;
     the footer link and the home hero button point to the same page.
   - The **Overview** row matches the database (products, published, out of stock,
     active/total promotions, orders) and lists the five most recently updated
     promotions; the page contains no form and no product table.
   - The **Actions** row shows four cards; each button opens its page (the
     catalogue, the wizard, the promotion manager, the admin order/product lists,
     the admin index).
   - On `/shop/` every card carries the staff toolbar: the stock line matches the
     shelf quantity and the held units, the title and **Edit** open the edit page,
     **Hide** removes the product from the shop and `/staff/` + `/shop/` counters
     drop by one.
   - Add a product, open **Show hidden products (1)** on `/shop/`: the deactivated
     card is listed with the **Hidden** badge, no "Add without customization"
     button and no **Hide** button, and **Show published products** goes back.
     More than `PRODUCTS_PAGE_SIZE` hidden products keep `?status=hidden` in the
     page links.
   - Sign out (or sign in as a customer) and open `/shop/?status=hidden`: the
     hidden products are not listed and the toggle is gone.
   - A product without a promotion shows **Add a promotion**, which opens
     `/promotions/create/?product=<id>` with the product and a
     "`<title>` bundle" name already filled in.
2. **Promotion manager (`/promotions/`)**
   - Search by promotion or product name and switch the status filter; **Clear**
     resets both.
   - Create a ladder (5 → 40.00, 10 → 70.00), press **Add a break** to get an
     extra row, then save: `/shop/` and `/` show the new badge and `/cart/` uses
     the break.
   - Try to save a break that is not a saving (e.g. 5 → 60.00 on a EUR 10
     product) and an empty ladder: both stay on the page with a readable error
     and nothing is stored.
   - Edit the price of one break, delete another with the trash button and save;
     the saved ladder card shows the new unit price and the saving percentage.
   - Delete the promotion from the modal: the ladder disappears and the product
     is back to its base price on the catalogue, the product page and the cart.
   - As a signed-in customer, the same URLs return `403`; signed out they redirect
     to the login page.
3. **Checkout**
   - Add 7 units of a product with a 5-for-40 ladder: `/cart/` shows the discount,
     **Checkout** opens `/orders/checkout/` with the same total (EUR 60 for a EUR
     10 base price) and the last shipping address prefilled.
   - Place the order: `/orders/` lists it with its units, total and payment
     status, the cart is empty and the catalogue availability dropped by 7 (not
     by 5).
   - Put more units in the cart than are available (`stock_quantity`) and place
     the order: the page comes back with "Only N of … can be ordered right now",
     no order is created and the stock is unchanged.
   - With a product held by a reserved order
     (`Product.objects.filter(pk=…).update(reserved_quantity=…)` in the shell),
     the catalogue shows the reduced availability and adding the last units fails
     with **Not enough stock**.


---

## Roadmap

- Add Django Ninja API app and payment endpoints.
- Integrate Stripe checkout and webhook pipeline (the stock cycle is ready: see
  [Ready for Stripe](#ready-for-stripe)).
- Add shipment tracking integration.
- Add a customer-facing order detail page with print-file download.

---

## License

MIT (see [LICENSE](./LICENSE)).
