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

test.describe('Admin equipment-types CRUD', () => {
  test('create → search → edit → delete a record', async ({ page }) => {
    const NEW_NAME = `E2E-EQ-${Date.now()}`
    const RENAMED = `${NEW_NAME}-renamed`

    // Arrange
    await loginAsAdmin(page)
    await page.goto('/admin/equipment-types')
    // Page header (anchored on the page-header-title CSS class to avoid
    // strict-mode collisions with sidebar/breadcrumb).
    await expect(page.locator('.ant-page-header-heading-title')).toContainText(
      '設備類型',
    )

    // Act — open create modal
    await page.getByRole('button', { name: re('新增') }).click()
    const dialog = page.locator('.ant-modal-wrap').filter({ has: page.getByRole('textbox') })
    await dialog.getByRole('textbox').first().fill(NEW_NAME)
    await dialog.getByRole('button', { name: re('儲存') }).click()
    // Assert — row visible
    await expect(page.getByText(NEW_NAME).first()).toBeVisible({ timeout: 10000 })

    // Search narrows
    await page.getByPlaceholder('依名稱搜尋').fill(NEW_NAME)
    await page.keyboard.press('Enter')
    await expect(page.getByRole('row', { name: new RegExp(NEW_NAME) })).toBeVisible()

    // Edit — click 編輯 in the matching row
    const targetRow = page.getByRole('row', { name: new RegExp(NEW_NAME) })
    await targetRow.getByRole('button', { name: re('編輯') }).click()
    const editDialog = page.locator('.ant-modal-wrap').filter({ has: page.getByRole('textbox') })
    const nameInput = editDialog.getByRole('textbox').first()
    await nameInput.fill(RENAMED)
    await editDialog.getByRole('button', { name: re('儲存') }).click()
    await expect(page.getByText(RENAMED).first()).toBeVisible({ timeout: 10000 })

    // Delete — click 刪除 then confirm popconfirm
    const renamedRow = page.getByRole('row', { name: new RegExp(RENAMED) })
    await renamedRow.getByRole('button', { name: re('刪除') }).click()
    // Popconfirm's "刪除" button is the second one to render after click
    await page.locator('.ant-popconfirm .ant-btn-dangerous').click()
    // The renamed row should disappear
    await expect(page.getByText(RENAMED)).toHaveCount(0, { timeout: 10000 })
  })
})
