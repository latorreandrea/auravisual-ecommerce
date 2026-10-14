/**
 * AuraVisual Ecommerce - shared frontend behaviour.
 *
 * Ecommerce variant of the AuraVisual main.js: AOS (Animate On Scroll) is
 * intentionally NOT used here. The animation layer is defined separately, so
 * this file only keeps the layout/interaction behaviour shared with the
 * baseline: fixed header state, mobile navigation and section scroll-spy.
 */
document.addEventListener('DOMContentLoaded', function () {
  const selectHeader = document.querySelector('#header');
  const selectMobileNav = document.querySelector('.mobile-nav-toggle');
  const selectNavbarNav = document.querySelector('.navbar');

  // ----------------------------------------------------------- Header state
  function headerScrolled() {
    if (!selectHeader) {
      return;
    }

    if (window.scrollY > 100) {
      selectHeader.classList.add('header-scrolled');
    } else {
      selectHeader.classList.remove('header-scrolled');
    }
  }

  headerScrolled();
  document.addEventListener('scroll', headerScrolled);

  // ------------------------------------------------------------- Mobile nav
  function closeMobileNav() {
    if (!selectNavbarNav || !selectMobileNav) {
      return;
    }

    selectNavbarNav.classList.remove('navbar-mobile');
    selectMobileNav.classList.add('bi-list');
    selectMobileNav.classList.remove('bi-x');
  }

  if (selectMobileNav) {
    selectMobileNav.addEventListener('click', function () {
      if (!selectNavbarNav) {
        return;
      }

      selectNavbarNav.classList.toggle('navbar-mobile');
      this.classList.toggle('bi-list');
      this.classList.toggle('bi-x');
    });
  }

  // Close the mobile menu as soon as a navigation link is clicked.
  document.querySelectorAll('.navbar .nav-link').forEach(function (link) {
    link.addEventListener('click', function () {
      if (selectNavbarNav && selectNavbarNav.classList.contains('navbar-mobile')) {
        closeMobileNav();
      }
    });
  });

  // Expand dropdowns on mobile instead of leaving the page immediately.
  document.querySelectorAll('.navbar .dropdown > a').forEach(function (el) {
    el.addEventListener('click', function (event) {
      if (selectNavbarNav && selectNavbarNav.classList.contains('navbar-mobile')) {
        event.preventDefault();

        const next = this.nextElementSibling;
        if (next) {
          next.classList.toggle('dropdown-active');
        }
      }
    });
  });

  // ------------------------------------------------------------ Scroll spy
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.nav-link.scrollto');

  if (!navLinks.length) {
    return;
  }

  window.addEventListener('scroll', function () {
    let current = '';

    sections.forEach(function (section) {
      const sectionTop = section.offsetTop - 80;
      const sectionHeight = section.offsetHeight;

      if (window.scrollY >= sectionTop && window.scrollY < sectionTop + sectionHeight) {
        current = section.getAttribute('id');
      }
    });

    navLinks.forEach(function (link) {
      link.classList.remove('active');

      if (link.getAttribute('href') === '#' + current) {
        link.classList.add('active');
      }
    });
  });
});
