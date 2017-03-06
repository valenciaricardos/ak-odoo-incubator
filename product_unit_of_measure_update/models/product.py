# coding: utf-8
# © 2016 David BEAL @ Akretion <david.beal@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import logging

from openerp import models, api, _
from openerp.exceptions import Warning as UserError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.multi
    def write(self, vals):
        if 'uom_id' in vals or 'uom_po_id' in vals:
            # We perform a more complex check only if applied to one record
            if len(self._ids) == 1:
                self._uom_category_check(vals)
            # Otherwise standard _check_uom() is finally called
        return super(ProductTemplate, self).write(vals)

    def _uom_category_check(self, vals):
        # here is the equivalent to standard _check_uom()
        # but before the write operation
        uom = self.env['product.uom'].browse(
            vals.get('uom_id', self.uom_id.id))
        uom_po = self.env['product.uom'].browse(
            vals.get('uom_po_id', self.uom_po_id.id))
        # We now have in uom and uom_po the final value of these fields
        if uom.category_id != uom_po.category_id:
            # Standard check fails, we switch to a clever check.
            self._set_new_uom(
                # By removing these keys we bypass standard check
                vals.pop('uom_id', None), vals.pop('uom_po_id', None))

    def _set_new_uom(self, uom_id, uom_po_id):
        product_in_model = self._products_used_in_db()
        if product_in_model:
            raise UserError(_(
                "This product is used in '%s' model.\nImpossible "
                "to modify the unit of measure." % product_in_model.name))
        sql_set_fields = []
        params = []
        if uom_id:
            sql_set_fields.append("uom_id=%s")
            params.append(uom_id)
        elif uom_po_id:
            sql_set_fields.append("uom_po_id=%s")
            params.append(uom_po_id)
        params.append(tuple(self.ids),)
        query = """UPDATE product_template SET {} WHERE id in %s""".format(
            ", ".join(sql_set_fields))
        self._cr.execute(query, params)
        _logger.info(" >>> Update product unit %s, %s" % (query, params))
        self.invalidate_cache()

    @api.multi
    def _products_used_in_db(self):
        used_products = False
        for product in self:
            # Optimization could be done here by searching first tables
            # where there is a higher probability to contains products data
            # recently created like:
            # stock.move, mrp.bom.line, sale.order.line
            # NotImplementForNow
            erp_fields = self.env['ir.model.fields'].search([
                ('relation', '=', 'product.product'),
                ('model_id.model', 'not in',
                    self._exclude_models_with_product_foreign_key()),
                ('ttype', '=', 'many2one')])
            # erp_fields contains all m2o to product.template
            for field in erp_fields:
                # we search in all tables using this m2o
                res = self.env[field.model_id.model].search(
                    [(field.name, 'in', product.product_variant_ids.ids)])
                used_products = used_products or len(res)
                if used_products:
                    # product used once is sufficient to stop checking
                    return field.model_id
        return False

    @api.model
    def _exclude_models_with_product_foreign_key(self):
        """ List of models on which no check are required
            because another model with m2o is defined on it
            You can customized this list according to
            your instance dependencies.
        """
        return [
            'report.stock.lines.date',  # dependency on stock.move first
        ]
