/* 03 - Core tables (star schema) and the load log.
   Careful: this drops and recreates everything in core. */
USE LakesideHospital;
GO

DROP TABLE IF EXISTS core.FactPayment;
DROP TABLE IF EXISTS core.FactCharge;
DROP TABLE IF EXISTS core.FactAdmission;
DROP TABLE IF EXISTS core.DimPatient;
DROP TABLE IF EXISTS core.DimTariff;
DROP TABLE IF EXISTS core.DimFunder;
DROP TABLE IF EXISTS core.DimDoctor;
DROP TABLE IF EXISTS core.DimWard;
DROP TABLE IF EXISTS core.DimDate;
DROP TABLE IF EXISTS audit.LoadLog;
GO

CREATE TABLE core.DimDate (
    DateKey         int          NOT NULL CONSTRAINT PK_DimDate PRIMARY KEY,   -- yyyymmdd
    FullDate        date         NOT NULL CONSTRAINT UQ_DimDate_FullDate UNIQUE,
    DayName         nvarchar(10) NOT NULL,
    MonthNumber     tinyint      NOT NULL,
    MonthName       nvarchar(10) NOT NULL,
    CalendarQuarter tinyint      NOT NULL,
    CalendarYear    smallint     NOT NULL,
    IsWeekend       bit          NOT NULL
);

-- the resources: wards (beds) and doctors
CREATE TABLE core.DimWard (
    WardKey                 int IDENTITY(1,1) NOT NULL CONSTRAINT PK_DimWard PRIMARY KEY,
    WardCode                varchar(10)  NOT NULL CONSTRAINT UQ_DimWard UNIQUE,
    WardName                nvarchar(60) NULL,
    WardType                nvarchar(30) NULL,
    BedCount                int          NOT NULL,
    AccommodationTariffCode varchar(10)  NOT NULL     -- which tariff a night in this ward is charged at
);

CREATE TABLE core.DimDoctor (
    DoctorKey  int IDENTITY(1,1) NOT NULL CONSTRAINT PK_DimDoctor PRIMARY KEY,
    DoctorID   varchar(10)   NOT NULL CONSTRAINT UQ_DimDoctor UNIQUE,
    DoctorName nvarchar(100) NULL,
    Speciality nvarchar(50)  NULL
);

-- who pays: a medical aid plan, or the patient (PRIV)
CREATE TABLE core.DimFunder (
    FunderKey  int IDENTITY(1,1) NOT NULL CONSTRAINT PK_DimFunder PRIMARY KEY,
    FunderCode varchar(10)   NOT NULL CONSTRAINT UQ_DimFunder UNIQUE,
    FunderName nvarchar(100) NULL,
    FunderType nvarchar(30)  NULL,
    CoverPct   decimal(5,2)  NOT NULL     -- % of covered charges the funder pays
);

-- the price list. one row per tariff code per effective date, so rates can change over time
CREATE TABLE core.DimTariff (
    TariffKey       int IDENTITY(1,1) NOT NULL CONSTRAINT PK_DimTariff PRIMARY KEY,
    TariffCode      varchar(10)   NOT NULL,
    Description     nvarchar(100) NULL,
    Category        nvarchar(30)  NULL,
    UnitOfMeasure   nvarchar(20)  NULL,
    Rate            decimal(10,2) NOT NULL,
    IsFunderCovered bit           NOT NULL,
    EffectiveFrom   date          NOT NULL,
    EffectiveTo     date          NOT NULL,
    CONSTRAINT UQ_DimTariff UNIQUE (TariffCode, EffectiveFrom)
);

CREATE TABLE core.DimPatient (
    PatientKey  int IDENTITY(1,1) NOT NULL CONSTRAINT PK_DimPatient PRIMARY KEY,
    PatientID   varchar(10)   NOT NULL CONSTRAINT UQ_DimPatient UNIQUE,
    FullName    nvarchar(100) NULL,
    DateOfBirth date          NULL,
    Gender      char(1)       NULL,
    City        nvarchar(50)  NULL
);

-- one row per admission. an admission is also the account that gets billed
CREATE TABLE core.FactAdmission (
    AdmissionKey      int IDENTITY(1,1) NOT NULL CONSTRAINT PK_FactAdmission PRIMARY KEY,
    AdmissionID       varchar(12)  NOT NULL CONSTRAINT UQ_FactAdmission UNIQUE,
    PatientKey        int          NOT NULL CONSTRAINT FK_Admission_Patient REFERENCES core.DimPatient (PatientKey),
    WardKey           int          NOT NULL CONSTRAINT FK_Admission_Ward    REFERENCES core.DimWard (WardKey),
    DoctorKey         int          NOT NULL CONSTRAINT FK_Admission_Doctor  REFERENCES core.DimDoctor (DoctorKey),
    FunderKey         int          NOT NULL CONSTRAINT FK_Admission_Funder  REFERENCES core.DimFunder (FunderKey),
    AdmitDateKey      int          NOT NULL CONSTRAINT FK_Admission_AdmitDate REFERENCES core.DimDate (DateKey),
    DischargeDateKey  int          NULL     CONSTRAINT FK_Admission_DischDate REFERENCES core.DimDate (DateKey),
    AdmitDateTime     datetime2(0) NOT NULL,
    DischargeDateTime datetime2(0) NULL,
    LengthOfStayDays  int          NULL,     -- NULL while the patient is still in hospital
    AuthorisationNo   varchar(20)  NULL,
    AdmissionType     varchar(20)  NULL,
    DiagnosisGroup    nvarchar(60) NULL
);

-- one row per charge line
CREATE TABLE core.FactCharge (
    ChargeKey      bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_FactCharge PRIMARY KEY,
    ChargeSource   varchar(15)   NOT NULL,    -- 'Captured' (from the charge files) or 'Accommodation' (worked out from the stay)
    SourceChargeID varchar(12)   NULL,
    AdmissionKey   int           NOT NULL CONSTRAINT FK_Charge_Admission REFERENCES core.FactAdmission (AdmissionKey),
    ServiceDateKey int           NOT NULL CONSTRAINT FK_Charge_Date      REFERENCES core.DimDate (DateKey),
    TariffKey      int           NOT NULL CONSTRAINT FK_Charge_Tariff    REFERENCES core.DimTariff (TariffKey),
    Quantity       decimal(9,2)  NOT NULL,
    Rate           decimal(10,2) NOT NULL,
    Amount         decimal(12,2) NOT NULL,    -- Quantity * Rate
    FunderAmount   decimal(12,2) NOT NULL,    -- the part the funder owes
    PatientAmount  decimal(12,2) NOT NULL     -- the part the patient owes
);
CREATE INDEX IX_FactCharge_Admission ON core.FactCharge (AdmissionKey);
CREATE INDEX IX_FactCharge_SourceID  ON core.FactCharge (SourceChargeID);

CREATE TABLE core.FactPayment (
    PaymentKey     int IDENTITY(1,1) NOT NULL CONSTRAINT PK_FactPayment PRIMARY KEY,
    PaymentID      varchar(12)   NOT NULL CONSTRAINT UQ_FactPayment UNIQUE,
    AdmissionKey   int           NOT NULL CONSTRAINT FK_Payment_Admission REFERENCES core.FactAdmission (AdmissionKey),
    PaymentDateKey int           NOT NULL CONSTRAINT FK_Payment_Date      REFERENCES core.DimDate (DateKey),
    PayerType      varchar(10)   NOT NULL,
    PaymentMethod  varchar(20)   NULL,
    Amount         decimal(12,2) NOT NULL
);
CREATE INDEX IX_FactPayment_Admission ON core.FactPayment (AdmissionKey);

CREATE TABLE audit.LoadLog (
    LoadLogID    int IDENTITY(1,1) NOT NULL CONSTRAINT PK_LoadLog PRIMARY KEY,
    StepName     sysname        NOT NULL,
    StartTime    datetime2(0)   NOT NULL,
    EndTime      datetime2(0)   NOT NULL,
    RowsAffected int            NOT NULL,
    LoadStatus   varchar(10)    NOT NULL,
    ErrorMessage nvarchar(4000) NULL
);
GO
