#include "_record.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>

#include <callback.h>
#include <dbAccess.h>
#include <dbCommon.h>
#include <dbScan.h>
#include <recSup.h>

#include "_interface.h"

static void process_callback(void *data) {
    dbCommon *rec = (dbCommon *)data;
    struct typed_rset *rset = (struct typed_rset *)rec->rset;
    rset->process(rec);
}

void fer_epics_record_init(dbCommon *rec, FerEpicsRecordType type, FerEpicsVar *var_info) {
    FerEpicsRecordDpvt *dpvt = (FerEpicsRecordDpvt *)malloc(sizeof(FerEpicsRecordDpvt));
    assert(dpvt != NULL);

    dpvt->type = type;
    dpvt->ioscan_list = NULL;
    dpvt->var_info = var_info;
    dpvt->user_data = NULL;

    callbackSetCallback(process_callback, &dpvt->process);
    callbackSetUser((void *)rec, &dpvt->process);
    callbackSetPriority(priorityLow, &dpvt->process);

    assert(rec->dpvt == NULL);
    rec->dpvt = dpvt;

    fer_var_init((FerVar *)rec);
}

void fer_epics_record_deinit(dbCommon *rec) {
    if (rec->dpvt != NULL) {
        FerEpicsRecordDpvt *dpvt = fer_epics_record_dpvt(rec);
        if (dpvt->var_info != NULL) {
            free((void *)dpvt->var_info);
        }
        free((void *)rec->dpvt);
        rec->dpvt = NULL;
    }
}

FerEpicsRecordDpvt *fer_epics_record_dpvt(dbCommon *rec) {
    FerEpicsRecordDpvt *dpvt = (FerEpicsRecordDpvt *)rec->dpvt;
    assert(dpvt != NULL);
    return dpvt;
}

FerEpicsVar *fer_epics_record_var_info(dbCommon *rec) {
    FerEpicsVar *var_info = fer_epics_record_dpvt(rec)->var_info;
    assert(var_info != NULL);
    return var_info;
}

IOSCANPVT fer_epics_record_ioscan_create(dbCommon *rec) {
    FerEpicsRecordDpvt *dpvt = fer_epics_record_dpvt(rec);

    IOSCANPVT ioscan_list;
    scanIoInit(&ioscan_list);
    dpvt->ioscan_list = ioscan_list;
    return ioscan_list;
}

void fer_epics_record_request_proc(dbCommon *rec) {
    FerEpicsRecordDpvt *dpvt = fer_epics_record_dpvt(rec);
    if (dpvt->ioscan_list != NULL) {
        scanIoRequest(dpvt->ioscan_list);
    }
}

void fer_epics_record_process(dbCommon *rec) {
    if (!rec->pact) {
        dbScanLock(rec);
        rec->pact = true;
        fer_var_proc_start((FerVar *)rec);
    } else {
        rec->pact = false;
        dbScanUnlock(rec);
    }
}

void fer_epics_record_proc_done(dbCommon *rec) {
    callbackRequest(&fer_epics_record_dpvt(rec)->process);
}
