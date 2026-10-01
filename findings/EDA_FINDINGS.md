# Google Play review EDA findings

## Scope and provenance

- **Collection run:** `20261001T002211Z_ad8670fc` (1 October 2026, UTC).
- **Collection design:** Google Play's newest reviews, configured for US / English, with a target of 500 per configured app.
- **Realized coverage:** 5,500 clean reviews from 11 apps in seven categories. Eleven apps returned 500 reviews each. Coursera returned zero records in this collection and is therefore excluded from the comparisons.
- **Source limitation:** collection uses the unofficial third-party `google-play-scraper` library, not a Google-supported API. The data is a dated convenience sample and is not representative of all users, countries, languages, or historical reviews.

## 1. Review characteristics

- Ratings are polarized: 2,575 reviews (46.8%) have five stars and 1,837 (33.4%) have one star. Together they account for 80.2% of the sample. The overall mean rating is 3.28 and the median is 4.
- Review text is right-skewed. The median length is 56 characters, while the mean is 108.4; the 90th and 95th percentiles are 305 and 417 characters, respectively.
- Retained review timestamps range from 8 March 2025 to 29 September 2026. The collector was set to newest-first, but the visible time range should still be reported rather than treated as a complete history.

## 2. Metadata coverage

| Field | Coverage | Interpretation |
| --- | ---: | --- |
| Rating | 100.0% | Available for every retained review. |
| Review timestamp | 100.0% | Available for every retained review. |
| Helpful-vote count | 100.0% | Available for every retained review. |
| App version | 85.6% | Strong but incomplete technical context. |
| Developer reply / reply timestamp | 13.3% | Sparse overall; absence is a product behavior, not necessarily a defect. |
| Review update timestamp | 0.0% | Not returned in this run, so it should not be used downstream. |

## 3. Data quality

- Raw rows read: **5,500**; clean rows retained: **5,500** (100.0%).
- Malformed JSONL rows: **0**; blank review text: **0**; invalid ratings: **0**; duplicate app/review keys removed: **0**.
- Database checks found zero blank stored texts, zero ratings outside 1-5, and zero duplicate `(app_id, source_review_id)` keys.
- The raw result is limited by a single collection run, newest-first ordering, US/English configuration, an unavailable Coursera sample, platform moderation, and the unofficial collection dependency.

## 4. Meaningful differences across apps and categories

| Category | Reviews | Average rating | Median text length |
| --- | ---: | ---: | ---: |
| Shopping | 1,000 | 2.61 | 98.5 |
| Health & Fitness | 1,000 | 2.71 | 108.5 |
| Music & Audio | 500 | 2.79 | 74.0 |
| Social | 1,000 | 3.16 | 49.0 |
| Travel & Local | 1,000 | 3.87 | 27.0 |
| Entertainment | 500 | 4.19 | 29.0 |
| Education | 500 | 4.44 | 29.5 |

- Average category ratings span 1.83 points, from Shopping (2.61) to Education (4.44). These are descriptive sample differences, not causal or population-quality rankings.
- Health & Fitness and Shopping have much longer median reviews than Travel & Local, Entertainment, and Education, indicating that a downstream text model should not assume equal information density across categories.
- Developer-reply coverage varies sharply by app: MyFitnessPal is 96.0%, Discord is 38.4%, Spotify is 10.8%, and several apps are at or near zero. The field is suitable for optional analysis, not a required feature.

## Recommended next step

Keep the current schema and use the fully populated rating, timestamp, text, and helpful-vote fields as the baseline for labeling and exploratory modeling. Before generalizing results or training a production model, add scheduled collections, diversify country/language configurations, investigate the Coursera retrieval gap, and monitor the unofficial collector for changes.
