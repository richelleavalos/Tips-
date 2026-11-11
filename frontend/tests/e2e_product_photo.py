"""Regression: real product photos must not loop the modal MutationObserver.
Run against a local QA database containing the product created in the Browser audit.
"""
import json, os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
base=os.getenv('TIPS_TEST_BASE_URL','http://127.0.0.1:8002')
assert urlsplit(base).hostname in {'localhost','127.0.0.1'}
out=Path(os.environ['TIPS_EVIDENCE_DIR']);out.mkdir(parents=True,exist_ok=True)
results=[]
with sync_playwright() as p:
    for engine in ['chromium','webkit']:
        browser=getattr(p,engine).launch()
        for w,h in [(1440,900),(768,1024),(390,844)]:
            context=browser.new_context(viewport={'width':w,'height':h});page=context.new_page();page.set_default_timeout(12000)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base+'/tienda.html')
            page.locator('[data-product="9"]').click()
            expect(page.locator('[data-modal-add]')).to_be_enabled()
            expect(page.locator('[data-modal-visual] img')).to_have_attribute('alt','Fotografía de lámpara del producto QA')
            expect(page.locator('[data-modal-price]')).to_contain_text('19.50')
            # A second UI action and image decode prove the event loop remains responsive.
            expect(page.locator('[data-modal-visual] img')).to_have_js_property('complete',True)
            page.screenshot(path=str(out/f'foto-{engine}-{w}.png'))
            page.locator('[data-modal-close]').click()
            page.locator('[data-product="1"]').click()
            expect(page.locator('[data-modal-add]')).to_be_enabled()
            expect(page.locator('[data-modal-visual] img[alt="Fotografía de lámpara del producto QA"]')).to_have_count(0)
            page.locator('[data-modal-close]').click()
            page.locator('[data-product="9"]').click();expect(page.locator('[data-modal-add]')).to_be_enabled()
            page.locator('[data-modal-add]').click()
            expect(page.locator('[data-cart-drawer]')).to_have_class(__import__('re').compile('is-open'))
            page.goto(base+'/checkout.html');f=page.locator('[data-checkout-form]')
            f.locator('[name=customer_name]').fill('QA fotografía '+engine+' '+str(w));f.locator('[name=phone]').fill('71234567')
            f.locator('[type=submit]').click();expect(page.locator('[data-order-success]')).to_have_class(__import__('re').compile('is-open'))
            expect(page.locator('[data-order-total]')).to_contain_text('19.50')
            page.locator('[data-tracking-link]').click();expect(page.locator('[data-detail]')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth')<=w+2
            assert not errors,errors
            results.append({'engine':engine,'width':w,'result':'PASS','photo_modal_switch_cart_checkout_tracking':True})
            context.close()
        browser.close()
(out/'photo-regression.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
