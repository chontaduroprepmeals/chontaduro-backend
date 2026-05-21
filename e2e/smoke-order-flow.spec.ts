import { expect, Page, test } from '@playwright/test';

async function completeToReview(page: Page, days = 6) {
  await page.goto('/');

  const zipModal = page.locator('#zipModalOverlay');
  await expect(zipModal).toBeVisible();

  await page.fill('#zipInput', '98101');
  await page.click('#zipTryBtn');
  await expect(zipModal).toBeHidden({ timeout: 20_000 });

  const zipBanner = page.locator('#zipBanner');
  await expect(zipBanner).toBeHidden();

  await page.locator('.diet-card[data-value="Omnivore"]').click();
  await page.locator('form#f button[type="submit"]').click();

  await page.locator('.plan-card[data-value="Plan 4: 2 main meals + 1 breakfast (full day)"]').click();
  await page.locator('form#f button[type="submit"]').click();

  await page.locator('.objective-card[data-value="Lose Fat"]').click();
  await page.locator('form#f button[type="submit"]').click();

  await page.locator('form#f button[type="submit"]').click();

  await page.fill('#weight_input', '70');
  await page.fill('#height_input', '175');
  await page.fill('input[name="age"]', '30');
  await page.locator('.sex-card[data-value="male"]').click();
  await page.locator('button[onclick="adjustDays(1)"]').click();
  await page.locator('button[onclick="adjustDays(1)"]').click();
  await page.locator('button[onclick="adjustDays(1)"]').click();
  await page.locator('.duration-card[data-value="30-60"]').click();
  await page.locator('.intensity-card[data-value="moderate"]').click();
  await page.locator('#personal_form button[type="submit"]').click();

  await page.locator(`[data-days="${days}"]`).click();
  await page.locator('form#f button[type="submit"]').click();

  await expect(page.getByText('Reviewing Your Information')).toBeVisible();
  await expect(zipBanner).toBeHidden();
}

test('smoke: zip banner scope, review back button, days persistence, and per-section edit links', async ({ page }) => {
  await completeToReview(page, 6);

  await expect(page.getByRole('button', { name: '← Back' }).first()).toBeVisible();
  await expect(page.getByText('6 days/week')).toBeVisible();

  await expect(page.locator("button[onclick*=\"editFromReview('plan')\"]")).toBeVisible();
  await expect(page.locator("button[onclick*=\"editFromReview('diet')\"]")).toBeVisible();
  await expect(page.locator("button[onclick*=\"editFromReview('body')\"]")).toBeVisible();
  await expect(page.locator("button[onclick*=\"editFromReview('activity')\"]")).toBeVisible();
  await expect(page.locator("button[onclick*=\"editFromReview('allergies')\"]")).toBeVisible();

  await page.locator("button[onclick*=\"editFromReview('plan')\"]").click();
  await expect(page.getByText('Choose the meal plan that fits your lifestyle')).toBeVisible();

  await completeToReview(page, 6);
  await page.locator("button[onclick*=\"editFromReview('diet')\"]").click();
  await expect(page.getByText('Choose the option that best describes your overall diet')).toBeVisible();

  await completeToReview(page, 6);
  await page.locator("button[onclick*=\"editFromReview('allergies')\"]").click();
  await expect(page.getByText('Allergies & Food Restrictions')).toBeVisible();

  await completeToReview(page, 6);
  await page.locator("button[onclick*=\"editFromReview('body')\"]").click();
  await expect(page.locator('#personal_form')).toBeVisible();

  await completeToReview(page, 6);
  await page.locator("button[onclick*=\"editFromReview('activity')\"]").click();
  await expect(page.locator('#personal_form')).toBeVisible();
});

test('smoke: meal card title sizing and checkout auth modal redesign + password toggle', async ({ page }) => {
  await completeToReview(page, 6);

  await page.getByRole('button', { name: '✨ Generate My Personalized Menu ✨' }).click();
  await expect(page.getByRole('button', { name: '🛒 Order Now' })).toBeVisible({ timeout: 60_000 });

  await expect(page.locator('.text-base.font-semibold.leading-snug').first()).toBeVisible();

  await page.getByRole('button', { name: '🛒 Order Now' }).click();
  await expect(page.locator('#checkoutModalOverlay')).toBeVisible();

  await expect(page.locator('#checkoutSignInTab')).toBeVisible();
  await expect(page.locator('#checkoutCreateTab')).toBeVisible();
  await expect(page.getByText('Secure Checkout')).toBeVisible();
  await expect(page.getByLabel('Email')).toBeVisible();
  await expect(page.getByLabel('Password')).toBeVisible();

  const passwordInput = page.locator('#checkoutPassword');
  const toggleButton = page.locator('#toggleCheckoutPasswordBtn');

  await expect(passwordInput).toHaveAttribute('type', 'password');
  await expect(toggleButton).toHaveText('Show');

  await toggleButton.click();
  await expect(passwordInput).toHaveAttribute('type', 'text');
  await expect(toggleButton).toHaveText('Hide');

  await toggleButton.click();
  await expect(passwordInput).toHaveAttribute('type', 'password');
  await expect(toggleButton).toHaveText('Show');
});
