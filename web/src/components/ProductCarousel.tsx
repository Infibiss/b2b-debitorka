import { useEffect, useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { publicText as t } from '../publicTypography';
import './product-carousel.css';

const slides = [
  {
    image: '/product/debtors.jpg',
    title: 'Должники и следующий шаг',
    text: 'Суммы, сроки и статусы — весь портфель перед вами.',
    alt: 'Реестр должников Mandato с остатками, сроками просрочки и следующими действиями',
  },
  {
    image: '/product/case.jpg',
    title: 'Каждый договор — отдельное дело',
    text: 'Обещание оплаты, спор и документы не смешиваются между договорами.',
    alt: 'Карточка должника Mandato с тремя договорами и независимыми статусами',
  },
  {
    image: '/product/portfolio.jpg',
    title: 'Главное о деньгах',
    text: 'Что просрочено, сколько обещали и сколько уже поступило.',
    alt: 'Обзор портфеля Mandato с показателями задолженности, оплатами и графиками',
  },
];
const INTERVAL = 8000;

export function ProductCarousel() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [visible, setVisible] = useState(false);
  const [pageVisible, setPageVisible] = useState(true);
  const [loaded, setLoaded] = useState<Set<string>>(() => new Set());
  const [failed, setFailed] = useState<Set<string>>(() => new Set());
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    const visibility = () => setPageVisible(!document.hidden);
    update();
    visibility();
    media.addEventListener('change', update);
    document.addEventListener('visibilitychange', visibility);
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      threshold: 0.25,
    });
    if (root.current) observer.observe(root.current);
    return () => {
      media.removeEventListener('change', update);
      document.removeEventListener('visibilitychange', visibility);
      observer.disconnect();
    };
  }, []);
  // Prerendered images can finish loading before React attaches event handlers.
  // Reconcile those results on mount and after changing the displayed images.
  useEffect(() => {
    const images = root.current?.querySelectorAll('img');
    const ready: string[] = [];
    const broken: string[] = [];
    images?.forEach((image) => {
      const src = image.getAttribute('src');
      if (!src || !image.complete) return;
      (image.naturalWidth > 0 ? ready : broken).push(src);
    });
    if (ready.length) setLoaded((current) => new Set([...current, ...ready]));
    if (broken.length) setFailed((current) => new Set([...current, ...broken]));
  }, [index]);
  const current = slides[index];
  const next = slides[(index + 1) % slides.length];
  const playing = !paused && !hovered && !focused && !reduced && visible && pageVisible;
  useEffect(() => {
    if (!playing || !loaded.has(next.image)) return;
    const timer = window.setTimeout(
      () => setIndex((value) => (value + 1) % slides.length),
      INTERVAL
    );
    return () => window.clearTimeout(timer);
  }, [playing, index, loaded, next.image]);
  function select(value: number) {
    setPaused(true);
    setIndex((value + slides.length) % slides.length);
  }
  function imageLoaded(src: string) {
    setLoaded((current) => new Set(current).add(src));
  }
  return (
    <section
      ref={root}
      className="product-carousel"
      aria-label={t('Экраны кабинета')}
      aria-roledescription={t('Карусель')}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false);
      }}
      onKeyDown={(event) => {
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          select(index + 1);
        }
        if (event.key === 'ArrowLeft') {
          event.preventDefault();
          select(index - 1);
        }
      }}
    >
      <div className="product-carousel-stage">
        {slides.map((slide, position) => {
          const active = position === index;
          const upcoming = position === (index + 1) % slides.length;
          return (
            <figure
              key={slide.image}
              className={`product-carousel-screen ${active ? 'is-active' : upcoming ? 'is-next' : 'is-hidden'}`}
              aria-hidden={!active}
              aria-roledescription={t('Слайд')}
              aria-label={t('Экран {0} из {1}', [position + 1, slides.length])}
            >
              {!failed.has(slide.image) ? (
                <img
                  src={slide.image}
                  srcSet={`${slide.image.replace('.jpg', '-320.webp')} 320w, ${slide.image.replace('.jpg', '-720.webp')} 720w, ${slide.image} 1440w`}
                  sizes="(max-width: 640px) 82vw, (max-width: 1200px) 76vw, 902px"
                  alt={active ? t(slide.alt) : ''}
                  width="1440"
                  height="1000"
                  loading="lazy"
                  decoding="async"
                  onLoad={() => imageLoaded(slide.image)}
                  onError={() => setFailed((current) => new Set(current).add(slide.image))}
                />
              ) : active ? (
                <div className="product-carousel-fallback">
                  <p>{t(slide.title)}</p>
                  <a href="/start?plan=trial">{t('Открыть свой кабинет')}</a>
                </div>
              ) : null}
            </figure>
          );
        })}
        <button
          className="product-carousel-peek"
          aria-label={t('Посмотреть следующий экран')}
          onClick={() => select(index + 1)}
        >
          <ArrowRight aria-hidden="true" size={24} />
        </button>
      </div>
      <div className="product-carousel-bottom">
        <div
          className="product-carousel-caption"
          aria-live={playing ? 'off' : 'polite'}
          aria-atomic="true"
        >
          <h3>{t(current.title)}</h3>
          <p>{t(current.text)}</p>
        </div>
      </div>
    </section>
  );
}
