import { expect, test } from '@playwright/test'

const ADMIN_USERNAME = 'admin'
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'Admin@LIMS_2026!Sup'

// Ant Design auto-inserts whitespace between CJK characters in button labels
// (`登入` is rendered as "登 入"). Regex selectors absorb this so the spec
// stays readable.
const submitBtn = (page) => page.getByRole('button', { name: /登\s*入/ })

test.describe('Authentication', () => {
  test('rejects empty submission with inline errors', async ({ page }) => {
    // Arrange
    await page.goto('/login')
    // Act — click submit with both fields empty
    await submitBtn(page).click()
    // Assert — antd Form rules surface the required-field message
    await expect(page.getByText('請輸入帳號')).toBeVisible()
    await expect(page.getByText('請輸入密碼')).toBeVisible()
  })

  test('shows error envelope on bad credentials', async ({ page }) => {
    // Arrange
    await page.goto('/login')
    // Act
    await page.getByPlaceholder('請輸入帳號').fill('not_a_user')
    await page.getByPlaceholder('請輸入密碼').fill('wrong-password')
    await submitBtn(page).click()
    // Assert — banner renders the backend message
    await expect(page.locator('.ant-alert')).toBeVisible({ timeout: 10000 })
    // Should remain on /login
    await expect(page).toHaveURL(/\/login/)
  })

  test('admin login lands on dashboard', async ({ page }) => {
    // Arrange
    await page.goto('/login')
    // Act
    await page.getByPlaceholder('請輸入帳號').fill(ADMIN_USERNAME)
    await page.getByPlaceholder('請輸入密碼').fill(ADMIN_PASSWORD)
    await submitBtn(page).click()
    // Assert — superuser sees the gradient admin entry button on dashboard
    await expect(page).toHaveURL('/')
    await expect(
      page.getByRole('button', { name: /管\s*理\s*後\s*台/ }).first(),
    ).toBeVisible()
  })
})
