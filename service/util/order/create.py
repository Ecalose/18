from enum import auto
from os import name
from service.database.models import TempOrder
from service.api.db import db

#调用支付接口
from service.util.pay.alipay.alipayf2f import AlipayF2F    #支付宝接口
from service.util.pay.hupijiao.xunhupay import Hupi     #虎皮椒支付接口
from service.util.pay.codepay.codepay import CodePay    #码支付
from service.util.pay.payjs.payjs import Payjs  #payjs接口
from service.util.pay.wechat.weixin import Wechat   # 微信官方
from service.util.pay.epay.common import Epay   # 易支付
from service.util.pay.mugglepay.mugglepay import Mugglepay
from service.util.pay.yungouos.yungou import YunGou 
from service.util.pay.vmq.vmpay import VMQ  # V免签 

#日志记录
from service.util.log import log
from service.util.order.handle import make_order
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(2)

from datetime import datetime,timedelta

def make_tmp_order(out_order_id,name,payment,contact,contact_txt,num):
    try:
        db.session.add(TempOrder(out_order_id,name,payment,contact,contact_txt,num,status=False,endtime=None))
        db.session.commit()
        return make_pay_url(out_order_id)
    except Exception as e:
        log(e)
        return False

def make_pay_url(out_order_id):
    order = TempOrder.query.filter_by(out_order_id = out_order_id).first()
    if order:
        res = order.to_json()
        payment = res['payment']
        name = res['name']
        total_price = res['total_price']
        r = pay_url(payment,name,out_order_id,total_price)
        if r:
            return r
    return False

def pay_url(payment,name,out_order_id,total_price):
    name = name.replace('=','_')  #防止k，v冲突       
    try:
        if payment == '支付宝当面付':
            # return jsonify({'qr_code':'455555555454deffffffff'})
            r = AlipayF2F().create_order(name,out_order_id,total_price)
        elif payment == '虎皮椒微信':
            r = Hupi().Pay(trade_order_id=out_order_id,total_fee=total_price,title=name)
        elif payment == '虎皮椒支付宝':
            r = Hupi(payment='alipay').Pay(trade_order_id=out_order_id,total_fee=total_price,title=name)
        elif payment in ['码支付微信','码支付支付宝','码支付QQ']:
            # 参数错误情况下，会失效
            r = CodePay().create_order(payment,total_price,out_order_id)
        elif payment in ['PAYJS支付宝','PAYJS微信']:
            r = Payjs().create_order(name,out_order_id,total_price)
        elif payment in ['V免签支付宝','V免签微信']:
            # 参数错误情况下，会失效
            if payment == 'V免签微信':
                r = VMQ().create_order(name,out_order_id,total_price)
            else:
                r = VMQ(payment='alipay').create_order(name,out_order_id,total_price)
        elif payment in ['微信官方接口']:
            r = Wechat().create_order(name,out_order_id,total_price)
        elif payment in ['易支付']:
            r = Epay().create_order(name,out_order_id,total_price)
        elif payment in ['Mugglepay']:
            r = Mugglepay().create_order(name,out_order_id,total_price)
        elif payment in ['YunGouOS']:   # 统一接口
            r = YunGou(payment='unity').create_order(name,out_order_id,total_price)
        elif payment in ['YunGouOS_WXPAY']:   # 微信接口
            r = YunGou().create_order_wxpay(name,out_order_id,total_price)
        else:
            return None 
        return r
    except Exception as e:
        log(e)
        return False    

def check_pay_status(payment,out_order_id,payjs_order_id):  # 加入时间戳
    try:
        if payment == '支付宝当面付':
            r = AlipayF2F().check(out_order_id)
        elif payment in ['虎皮椒支付宝','虎皮椒微信']:
            if payment == '虎皮椒微信':
                obj = Hupi()
            else:
                obj = Hupi(payment='alipay')
            r = obj.Check(out_trade_order=out_order_id)
        elif payment in ['码支付微信','码支付支付宝','码支付QQ']:
            r = CodePay().check(out_order_id)
        elif payment in ['PAYJS支付宝','PAYJS微信']:
            if payjs_order_id:
                r = Payjs().check(payjs_order_id)
        elif payment in ['V免签支付宝','V免签微信']:
            orderId = payjs_order_id
            r = VMQ().check(orderId)
        elif payment in ['微信官方接口']:
            r = Wechat().check(out_order_id)
        elif payment in ['易支付']:
            r = Epay().check(out_order_id)
        elif payment in ['Mugglepay']:
            r = Mugglepay().check(out_order_id)
        elif payment in ['YunGouOS','YunGouOS_WXPAY']:
            if payment == 'YunGouOS_WXPAY':
                r = YunGou().check(out_order_id)
            else:
                r = YunGou(payment='unity').check(out_order_id)
        else:
            return None
    except Exception as e:
        log(e)
        return False     
    if r:
        # 状态更新--订单创建
        executor.submit(success_card,out_order_id)   #success_card(out_order_id)
        return True
    return False   

def success_card(out_order_id):
    if not TempOrder.query.filter_by(out_order_id = out_order_id,status = True).count():    #保证一次
        TempOrder.query.filter_by(out_order_id = out_order_id).update({'status':True,'endtime':datetime.utcnow()+timedelta(hours=8)})
        db.session.commit()  
        # 订单创建
        res = TempOrder.query.filter_by(out_order_id = out_order_id,status = True).first()
        if res:
            name = res.to_json()['name']
            payment = res.to_json()['payment']
            contact = res.to_json()['contact']
            contact_txt = res.to_json()['contact_txt']
            price = res.to_json()['price']
            num = res.to_json()['num']
            total_price = res.to_json()['total_price']
            auto = res.to_json()['auto']
            make_order(out_order_id,name,payment,contact,contact_txt,price,num,total_price,auto)
        # 
        #     pass
    return 'OK'

