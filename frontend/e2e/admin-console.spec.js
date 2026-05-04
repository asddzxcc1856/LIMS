import { expect, test } from '@playwright/test'

const ADMIN_USERNAME = 'admin'
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'Admin@LIMS_2026!Sup'

// Ant Design pads spaces between CJK chars on buttons.
const re = (s) => new RegExp(s.split('').join('\\s*'))

async function loginAsAdmin(page) {
  await page.goto('/login')
  await page.getByPlaceholder('請輸入帳號').fill(ADMIN_USERNAME)
  await page.getByPlaceholder('請輸入密碼').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: re('登入') }).click()
  await expect(page).toHaveURL('/')
}

test.describe('Admin console', () => {
  test('dashboard renders KPI cards and recent activity', async ({ page }) => {
    // Arrange
    await loginAsAdmin(page)
    // Act
    await page.goto('/admin/dashboard')
    // Assert — page header (the title appears in sidebar/breadcrumb/page-header,
    // so anchor on the page-header element specifically) + KPI labels.
    await expect(page.locator('.ant-page-header-heading-title')).toContainText(
      '系統儀表板',
    )
    await expect(page.getByText('總訂單數')).toBeVisible()
    await expect(page.getByText('進行中訂單')).toBeVisible()
    await expect(page.getByText('設備使用率')).toBeVisible()
    await expect(page.getByText('最近活動')).toBeVisible()
  })

  test('activity log page loads with filter controls', async ({ page }) => {
    // Arrange
    await loginAsAdmin(page)
    await page.goto('/admin/logs')
    // Assert
    await expect(page.getByText('活動日誌').first()).toBeVisible()
    await expect(page.getByPlaceholder(/username/i)).toBeVisible()
    await expect(
      page.getByRole('button', { name: re('套用') }).or(
        page.getByRole('button', { name: re('重新整理') }),
      ).first(),
    ).toBeVisible()
  })

  test('navigates to admin sections via sidebar', async ({ page }) => {
    // Arrange
    await loginAsAdmin(page)
    await page.goto('/admin/dashboard')
    // Act / Assert — click each major sidebar item. menuitem accessible names
    // include the icon text ("team 使用者"), so anchor on the visible label.
    await page.locator('.ant-menu-item').filter({ hasText: '使用者' }).click()
    await expect(page).toHaveURL(/\/admin\/users/)

    // "設備" alone matches "設備類型" / "設備" / "設備預約". Use exact-match label.
    await page.locator('.ant-menu-item .ant-menu-title-content', { hasText: /^設備$/ })
      .click()
    await expect(page).toHaveURL(/\/admin\/equipment/)

    await page.locator('.ant-menu-item .ant-menu-title-content', { hasText: /^訂單$/ })
      .click()
    await expect(page).toHaveURL(/\/admin\/orders/)
  })

  test('non-superuser cannot reach /admin', async ({ page, request }) => {
    // Arrange — create a fresh non-admin user via the admin API while logged in
    await loginAsAdmin(page)
    const accessToken = await page.evaluate(() => localStorage.getItem('access_token'))
    const username = `e2e_employee_${Date.now()}`
    const password = 'E2eTesting2026!'
    const created = await request.post('http://127.0.0.1:8000/api/admin/users/', {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        username,
        email: `${username}@e2e.test`,
        password,
        role: 'regular_employee',
        status: 'active',
      },
    })
    expect(created.ok()).toBeTruthy()

    // Act — log out, log in as the new non-admin, try to visit /admin
    await page.evaluate(() => {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    })
    await page.goto('/login')
    await page.getByPlaceholder('請輸入帳號').fill(username)
    await page.getByPlaceholder('請輸入密碼').fill(password)
    await page.getByRole('button', { name: re('登入') }).click()
    await expect(page).toHaveURL('/')

    await page.goto('/admin/dashboard')
    // Assert — router guard sends them back to /
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('button', { name: re('管理後台') })).toHaveCount(0)
  })
})
