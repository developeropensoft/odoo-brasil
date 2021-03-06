# -*- coding: utf-8 -*-
# © 2016 Danimar Ribeiro <danimaribeiro@gmail.com>, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
from datetime import datetime
from odoo.exceptions import UserError
from odoo import api, fields, models
from odoo.addons import decimal_precision as dp
from odoo.addons.br_account.models.cst import CST_ICMS
from odoo.addons.br_account.models.cst import CSOSN_SIMPLES
from odoo.addons.br_account.models.cst import CST_IPI
from odoo.addons.br_account.models.cst import CST_PIS_COFINS
from odoo.addons.br_account.models.cst import ORIGEM_PROD


class InvoiceEletronic(models.Model):
    _name = 'invoice.eletronic'

    _inherit = ['mail.thread']

    code = fields.Char(u'Código', size=100, required=True)
    name = fields.Char(u'Nome', size=100, required=True)
    company_id = fields.Many2one('res.company', u'Empresa', index=True)
    state = fields.Selection([('draft', u'Provisório'),
                              ('error', 'Erro'),
                              ('done', 'Enviado'),
                              ('cancel', 'Cancelado')],
                             string=u'State', default='draft')

    tipo_operacao = fields.Selection([('entrada', 'Entrada'),
                                      ('saida', 'Saída')], u'Tipo emissão')
    model = fields.Selection([('55', '55 - NFe'),
                              ('65', '65 - NFCe'),
                              ('001', 'NFS-e - Nota Fiscal Paulistana')],
                             u'Modelo')
    serie = fields.Many2one('br_account.document.serie', string=u'Série')
    numero = fields.Integer(u'Número')
    numero_controle = fields.Integer(u'Número de Controle')
    data_emissao = fields.Datetime(u'Data emissão')
    data_fatura = fields.Datetime(u'Data Entrada/Saída')
    data_autorizacao = fields.Char(u'Data de autorização', size=30)

    ambiente = fields.Selection([('homologacao', u'Homologação'),
                                 ('producao', u'Produção')], u'Ambiente')
    finalidade_emissao = fields.Selection(
        [('1', u'1 - Normal'),
         ('2', u'2 - Complementar'),
         ('3', u'3 - Ajuste'),
         ('4', u'4 - Devolução')],
        u'Finalidade', help=u"Finalidade da emissão de NFe")
    invoice_id = fields.Many2one('account.invoice', u'Fatura')
    partner_id = fields.Many2one('res.partner', u'Parceiro')
    commercial_partner_id = fields.Many2one(
        'res.partner', string='Commercial Entity',
        related='partner_id.commercial_partner_id', store=True, readonly=True)
    partner_shipping_id = fields.Many2one('res.partner', u'Entrega')
    payment_term_id = fields.Many2one('account.payment.term',
                                      string=u'Forma pagamento')
    fiscal_position_id = fields.Many2one('account.fiscal.position',
                                         string=u'Posição Fiscal')

    eletronic_item_ids = fields.One2many('invoice.eletronic.item',
                                         'invoice_eletronic_id',
                                         string=u"Linhas")

    eletronic_event_ids = fields.One2many('invoice.eletronic.event',
                                          'invoice_eletronic_id',
                                          string=u"Eventos", readonly=True)

    valor_bruto = fields.Monetary(u'Total Produtos')
    valor_frete = fields.Monetary(u'Total Frete')
    valor_seguro = fields.Monetary(u'Total Seguro')
    valor_desconto = fields.Monetary(u'Total Desconto')
    valor_despesas = fields.Monetary(u'Total Despesas')
    valor_bc_icms = fields.Monetary(u"Base de Cálculo ICMS")
    valor_icms = fields.Monetary(u"Total do ICMS")
    valor_icms_deson = fields.Monetary(u'ICMS Desoneração')
    valor_bc_icmsst = fields.Monetary(
        u'Total Base ST', help=u"Total da base de cálculo do ICMS ST")
    valor_icmsst = fields.Monetary(u'Total ST')
    valor_ii = fields.Monetary(u'Total II')
    valor_ipi = fields.Monetary(u"Total IPI")
    valor_pis = fields.Monetary(u"Total PIS")
    valor_cofins = fields.Monetary(u"Total COFINS")
    valor_estimado_tributos = fields.Monetary(u"Tributos Estimados")

    valor_servicos = fields.Monetary(u"Total Serviços")
    valor_bc_issqn = fields.Monetary(u"Base ISS")
    valor_issqn = fields.Monetary(u"Total ISS")
    valor_pis_servicos = fields.Monetary(u"Total PIS Serviços")
    valor_cofins_servicos = fields.Monetary(u"Total Cofins Serviço")

    valor_retencao_issqn = fields.Monetary(u"Retenção ISSQN")
    valor_retencao_pis = fields.Monetary(u"Retenção PIS")
    valor_retencao_cofins = fields.Monetary(u"Retenção COFINS")
    valor_retencao_irrf = fields.Monetary(u"Retenção IRRF")
    valor_retencao_csll = fields.Monetary(u"Retenção CSLL")
    valor_retencao_previdencia = fields.Monetary(
        u"Retenção Prev.", help=u"Retenção Previdência Social")

    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id',
        string="Company Currency", readonly=True)
    valor_final = fields.Monetary(u'Valor Final')

    informacoes_legais = fields.Text(u'Informações legais')
    informacoes_complementares = fields.Text(u'Informações complementares')

    codigo_retorno = fields.Char(string=u'Código Retorno')
    mensagem_retorno = fields.Char(string=u'Mensagem Retorno')
    numero_nfe = fields.Char(string="Numero Formatado NFe")

    def _create_attachment(self, prefix, event, data):
        file_name = '%s-%s.xml' % (
            prefix, datetime.now().strftime('%Y-%m-%d-%H-%M'))
        self.env['ir.attachment'].create(
            {
                'name': file_name,
                'datas': base64.b64encode(data),
                'datas_fname': file_name,
                'description': u'',
                'res_model': 'invoice.eletronic',
                'res_id': event.id
            })

    @api.multi
    def _hook_validation(self):
        """
            Override this method to implement the validations specific
            for the city you need
            @returns list<string> errors
        """
        errors = []
        if not self.serie.fiscal_document_id:
            errors.append(u'Nota Fiscal - Tipo de documento fiscal')
        if not self.serie.internal_sequence_id:
            errors.append(u'Nota Fiscal - Número da nota fiscal, \
                          a série deve ter uma sequencia interna')

        # Emitente
        if not self.company_id.nfe_a1_file:
            errors.append(u'Emitente - Certificado Digital')
        if not self.company_id.nfe_a1_password:
            errors.append(u'Emitente - Senha do Certificado Digital')
        if not self.company_id.partner_id.legal_name:
            errors.append(u'Emitente - Razão Social')
        if not self.company_id.partner_id.cnpj_cpf:
            errors.append(u'Emitente - CNPJ/CPF')
        if not self.company_id.partner_id.street:
            errors.append(u'Emitente / Endereço - Logradouro')
        if not self.company_id.partner_id.number:
            errors.append(u'Emitente / Endereço - Número')
        if not self.company_id.partner_id.zip:
            errors.append(u'Emitente / Endereço - CEP')
        if not self.company_id.partner_id.state_id:
            errors.append(u'Emitente / Endereço - Estado')
        else:
            if not self.company_id.partner_id.state_id.ibge_code:
                errors.append(u'Emitente / Endereço - Cód. do IBGE do estado')
            if not self.company_id.partner_id.state_id.name:
                errors.append(u'Emitente / Endereço - Nome do estado')

        if not self.company_id.partner_id.city_id:
            errors.append(u'Emitente / Endereço - município')
        else:
            if not self.company_id.partner_id.city_id.name:
                errors.append(u'Emitente / Endereço - Nome do município')
            if not self.company_id.partner_id.city_id.ibge_code:
                errors.append(u'Emitente/Endereço - Cód. do IBGE do município')

        if not self.company_id.partner_id.country_id:
            errors.append(u'Emitente / Endereço - país')
        else:
            if not self.company_id.partner_id.country_id.name:
                errors.append(u'Emitente / Endereço - Nome do país')
            if not self.company_id.partner_id.country_id.bc_code:
                errors.append(u'Emitente / Endereço - Código do BC do país')

        partner = self.partner_id.commercial_partner_id
        company = self.company_id
        # Destinatário
        if partner.is_company and not partner.legal_name:
            errors.append(u'Destinatário - Razão Social')

        if partner.country_id.id == company.partner_id.country_id.id:
            if not partner.cnpj_cpf:
                errors.append(u'Destinatário - CNPJ/CPF')

        if not partner.street:
            errors.append(u'Destinatário / Endereço - Logradouro')

        if not partner.number:
            errors.append(u'Destinatário / Endereço - Número')

        if partner.country_id.id == company.partner_id.country_id.id:
            if not partner.zip:
                errors.append(u'Destinatário / Endereço - CEP')

        if partner.country_id.id == company.partner_id.country_id.id:
            if not partner.state_id:
                errors.append(u'Destinatário / Endereço - Estado')
            else:
                if not partner.state_id.ibge_code:
                    errors.append(u'Destinatário / Endereço - Código do IBGE \
                                  do estado')
                if not partner.state_id.name:
                    errors.append(u'Destinatário / Endereço - Nome do estado')

        if partner.country_id.id == company.partner_id.country_id.id:
            if not partner.city_id:
                errors.append(u'Destinatário / Endereço - Município')
            else:
                if not partner.city_id.name:
                    errors.append(u'Destinatário / Endereço - Nome do \
                                  município')
                if not partner.city_id.ibge_code:
                    errors.append(u'Destinatário / Endereço - Código do IBGE \
                                  do município')

        if not partner.country_id:
            errors.append(u'Destinatário / Endereço - País')
        else:
            if not partner.country_id.name:
                errors.append(u'Destinatário / Endereço - Nome do país')
            if not partner.country_id.bc_code:
                errors.append(u'Destinatário / Endereço - Cód. do BC do país')

        # produtos
        for eletr in self.eletronic_item_ids:
            if eletr.product_id:
                if not eletr.product_id.default_code:
                    errors.append(
                        u'Prod: %s - Código do produto' % (
                            eletr.product_id.name))
        return errors

    @api.multi
    def validate_invoice(self):
        self.ensure_one()
        errors = self._hook_validation()
        if len(errors) > 0:
            msg = u"\n".join(
                [u"Por favor corrija os erros antes de prosseguir"] + errors)
            raise UserError(msg)

    @api.multi
    def action_post_validate(self):
        pass

    @api.multi
    def _prepare_eletronic_invoice_item(self, item, invoice):
        return {}

    @api.multi
    def _prepare_eletronic_invoice_values(self):
        return {}

    @api.multi
    def action_send_eletronic_invoice(self):
        pass

    @api.multi
    def action_cancel_document(self, context=None, justificativa=None):
        pass

    @api.multi
    def action_back_to_draft(self):
        self.state = 'draft'

    @api.multi
    def unlink(self):
        for item in self:
            if item.state == 'done':
                raise UserError(
                    u'Documento Eletrônico enviado - Proibido excluir')
        super(InvoiceEletronic, self).unlink()

    def log_exception(self, exc):
        self.codigo_retorno = -1
        self.mensagem_retorno = exc.message

    @api.multi
    def cron_send_nfe(self):
        inv_obj = self.env['invoice.eletronic'].with_context({
            'lang': self.env.user.lang, 'tz': self.env.user.tz})
        nfes = inv_obj.search([('state', '=', 'draft')])
        for item in nfes:
            try:
                item.action_send_eletronic_invoice()
            except Exception as e:
                item.log_exception(e)


class InvoiceEletronicEvent(models.Model):
    _name = 'invoice.eletronic.event'
    _order = 'id desc'

    code = fields.Char(string=u'Código', readonly=True)
    name = fields.Char(string=u'Mensagem', readonly=True)
    invoice_eletronic_id = fields.Many2one('invoice.eletronic',
                                           string=u"Fatura Eletrônica")


class InvoiceEletronicItem(models.Model):
    _name = 'invoice.eletronic.item'

    name = fields.Char(u'Nome', size=100)
    company_id = fields.Many2one('res.company', u'Empresa', index=True)
    invoice_eletronic_id = fields.Many2one('invoice.eletronic', u'Documento')
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id',
        string="Company Currency", readonly=True)

    product_id = fields.Many2one('product.product', string=u'Produto')
    tipo_produto = fields.Selection([('product', 'Produto'),
                                     ('service', u'Serviço')],
                                    string="Tipo Produto")
    cfop = fields.Char(u'CFOP', size=5)
    ncm = fields.Char(u'NCM', size=10)

    uom_id = fields.Many2one('product.uom', u'Unidade de Medida')
    quantidade = fields.Float(u'Quantidade')
    preco_unitario = fields.Monetary(
        u'Preço Unitário', digits=dp.get_precision('Account'))

    frete = fields.Monetary(u'Frete', digits=dp.get_precision('Account'))
    seguro = fields.Monetary(u'Seguro', digits=dp.get_precision('Account'))
    desconto = fields.Monetary(u'Desconto', digits=dp.get_precision('Account'))
    outras_despesas = fields.Monetary(
        u'Outras despesas', digits=dp.get_precision('Account'))

    tributos_estimados = fields.Monetary(
        u'Valor Estimado Tributos', digits=dp.get_precision('Account'))

    valor_bruto = fields.Monetary(
        u'Valor Bruto', digits=dp.get_precision('Account'))
    valor_liquido = fields.Monetary(
        u'Valor Líquido', digits=dp.get_precision('Account'))
    indicador_total = fields.Selection(
        [('0', '0 - Não'), ('1', '1 - Sim')],
        string="Compõe Total da Nota?", default='1')

    origem = fields.Selection(ORIGEM_PROD, u'Origem Mercadoria')
    icms_cst = fields.Selection(
        CST_ICMS + CSOSN_SIMPLES, u'Situação Tributária')
    icms_aliquota = fields.Float(
        u'Alíquota', digits=dp.get_precision('Account'))
    icms_tipo_base = fields.Selection(
        [('0', u'0 - Margem Valor Agregado (%)'),
         ('1', u'1 - Pauta (Valor)'),
         ('2', u'2 - Preço Tabelado Máx. (valor)'),
         ('3', u'3 - Valor da operação')],
        u'Modalidade BC do ICMS')
    icms_base_calculo = fields.Monetary(
        u'Base de cálculo', digits=dp.get_precision('Account'))
    icms_aliquota_reducao_base = fields.Float(
        u'% Redução Base', digits=dp.get_precision('Account'))
    icms_valor = fields.Monetary(
        u'Valor Total', digits=dp.get_precision('Account'))
    icms_valor_credito = fields.Monetary(
        u"Valor de Cŕedito", digits=dp.get_precision('Account'))
    icms_aliquota_credito = fields.Float(
        u'% de Crédito', digits=dp.get_precision('Account'))

    icms_st_tipo_base = fields.Selection(
        [('0', u'0- Preço tabelado ou máximo  sugerido'),
         ('1', u'1 - Lista Negativa (valor)'),
         ('2', u'2 - Lista Positiva (valor)'),
         ('3', u'3 - Lista Neutra (valor)'),
         ('4', u'4 - Margem Valor Agregado (%)'), ('5', '5 - Pauta (valor)')],
        'Tipo Base ICMS ST', required=True, default='4')
    icms_st_aliquota_mva = fields.Float(
        u'% MVA', digits=dp.get_precision('Account'))
    icms_st_aliquota = fields.Float(
        u'Alíquota', digits=dp.get_precision('Account'))
    icms_st_base_calculo = fields.Monetary(
        u'Base de cálculo', digits=dp.get_precision('Account'))
    icms_st_aliquota_reducao_base = fields.Float(
        u'% Redução Base', digits=dp.get_precision('Account'))
    icms_st_valor = fields.Monetary(
        u'Valor Total', digits=dp.get_precision('Account'))

    icms_aliquota_diferimento = fields.Float(
        u'% Diferimento', digits=dp.get_precision('Account'))
    icms_valor_diferido = fields.Monetary(
        u'Valor Diferido', digits=dp.get_precision('Account'))

    icms_motivo_desoneracao = fields.Char(u'Motivo Desoneração', size=2)
    icms_valor_desonerado = fields.Monetary(
        u'Valor Desonerado', digits=dp.get_precision('Account'))

    # ----------- IPI -------------------
    ipi_cst = fields.Selection(CST_IPI, string=u'Situação tributária')
    ipi_aliquota = fields.Float(
        u'Alíquota', digits=dp.get_precision('Account'))
    ipi_base_calculo = fields.Monetary(
        u'Base de cálculo', digits=dp.get_precision('Account'))
    ipi_reducao_bc = fields.Float(
        u'% Redução Base', digits=dp.get_precision('Account'))
    ipi_valor = fields.Monetary(
        u'Valor Total', digits=dp.get_precision('Account'))

    # ----------- II ----------------------
    ii_base_calculo = fields.Monetary(
        u'Base de Cálculo', digits=dp.get_precision('Account'))
    ii_aliquota = fields.Float(
        u'Alíquota II', digits=dp.get_precision('Account'))
    ii_valor_despesas = fields.Monetary(
        u'Despesas Aduaneiras', digits=dp.get_precision('Account'))
    ii_valor = fields.Monetary(
        u'Imposto de Importação', digits=dp.get_precision('Account'))
    ii_valor_iof = fields.Monetary(u'IOF', digits=dp.get_precision('Account'))

    # ------------ PIS ---------------------
    pis_cst = fields.Selection(CST_PIS_COFINS, u'Situação Tributária')
    pis_aliquota = fields.Float(
        u'Alíquota', digits=dp.get_precision('Account'))
    pis_base_calculo = fields.Monetary(
        u'Base de Cálculo', digits=dp.get_precision('Account'))
    pis_valor = fields.Monetary(
        u'Valor Total', digits=dp.get_precision('Account'))

    # ------------ COFINS ------------
    cofins_cst = fields.Selection(CST_PIS_COFINS, u'Situação Tributária')
    cofins_aliquota = fields.Float(
        u'Alíquota', digits=dp.get_precision('Account'))
    cofins_base_calculo = fields.Monetary(
        u'Base de Cálculo', digits=dp.get_precision('Account'))
    cofins_valor = fields.Monetary(
        u'Valor Total', digits=dp.get_precision('Account'))

    # ----------- ISSQN -------------
    issqn_codigo = fields.Char(u'Código', size=10)
    issqn_aliquota = fields.Float(
        u'Alíquota', digits=dp.get_precision('Account'))
    issqn_base_calculo = fields.Monetary(
        u'Base de Cálculo', digits=dp.get_precision('Account'))
    issqn_valor = fields.Monetary(
        u'Valor Total', digits=dp.get_precision('Account'))
    issqn_valor_retencao = fields.Monetary(
        u'Valor Retenção', digits=dp.get_precision('Account'))
