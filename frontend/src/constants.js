export const ROLES={admin:'调拨主管',chemist:'化验员',viewer:'船代观察员'};
export const SAMPLE_STATES={received:'待比对',queued:'比对中',qualified:'原样合格',anomaly:'异常待复检',retested:'复检合格',rejected:'复检未过',failed:'计算失败'};
export const AUDIT_ACTIONS={tank_registered:'储罐登记',tank_state:'储罐状态调整',sample_received:'油样收件',sample_compared:'密度分布比对',sample_retested:'化验复检',transfer_requested:'调拨申请',transfer_released:'主管调拨放行',permit_planned:'清线计划',line_registered:'管线登记',line_permitted:'清线许可',window_planned:'受油窗口计划',window_confirmed:'泊位窗口确认',berth_registered:'泊位登记',harbor_occupied:'放行占用资源',harbor_completed:'输油完工释放',retained_sealed:'燃油留样封存',retest_commissioned:'封样复检委托',retest_reported:'委托检验报告',retest_closed:'委托复检结案',stratification_registered:'储罐分层登记',stratification_invalidated:'补油分层作废',layer_deducted:'放行分层扣量'};

export const RECEIPT_STATES={planned:'计划到港',inspected:'化验核对通过',received:'已入罐冻结'};
export const RECONCILIATION_STATES={matched:'容差内待签',variance:'超差待调查',closed:'主管已结案'};
export const LAYER_STATES={pending:'缺样/待判定',qualified:'合格可抽',anomaly:'异常留罐'};
export const STRAT_STATES={none:'未登记分层，按整罐存量放行',active:'分层在册，按罐底连续合格层放行',stale:'补油后原分层已作废，须重新分层取样'};
