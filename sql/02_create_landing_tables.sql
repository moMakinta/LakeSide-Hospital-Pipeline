/* 02 - Landing tables. Truncated and reloaded by the Python script on every run.
   No keys or constraints here on purpose. */
USE LakesideHospital;
GO

DROP TABLE IF EXISTS landing.Payment;
DROP TABLE IF EXISTS landing.Charge;
DROP TABLE IF EXISTS landing.Admission;
DROP TABLE IF EXISTS landing.Patient;
DROP TABLE IF EXISTS landing.Tariff;
DROP TABLE IF EXISTS landing.Funder;
DROP TABLE IF EXISTS landing.Doctor;
DROP TABLE IF EXISTS landing.Ward;
GO

CREATE TABLE landing.Ward (
    WardCode                varchar(10)   NOT NULL,
    WardName                nvarchar(60)  NULL,
    WardType                nvarchar(30)  NULL,
    BedCount                int           NOT NULL,
    AccommodationTariffCode varchar(10)   NOT NULL
);

CREATE TABLE landing.Doctor (
    DoctorID   varchar(10)   NOT NULL,
    DoctorName nvarchar(100) NULL,
    Speciality nvarchar(50)  NULL
);

CREATE TABLE landing.Funder (
    FunderCode varchar(10)   NOT NULL,
    FunderName nvarchar(100) NULL,
    FunderType nvarchar(30)  NULL,
    CoverPct   decimal(5,2)  NOT NULL
);

CREATE TABLE landing.Tariff (
    TariffCode      varchar(10)   NOT NULL,
    Description     nvarchar(100) NULL,
    Category        nvarchar(30)  NULL,
    UnitOfMeasure   nvarchar(20)  NULL,
    Rate            decimal(10,2) NOT NULL,
    IsFunderCovered bit           NOT NULL,
    EffectiveFrom   date          NOT NULL
);

CREATE TABLE landing.Patient (
    PatientID   varchar(10)   NOT NULL,
    FullName    nvarchar(100) NULL,
    DateOfBirth date          NULL,
    Gender      char(1)       NULL,
    City        nvarchar(50)  NULL
);

CREATE TABLE landing.Admission (
    AdmissionID       varchar(12)  NOT NULL,
    PatientID         varchar(10)  NOT NULL,
    WardCode          varchar(10)  NOT NULL,
    DoctorID          varchar(10)  NOT NULL,
    FunderCode        varchar(10)  NOT NULL,
    AuthorisationNo   varchar(20)  NULL,
    AdmitDateTime     datetime2(0) NOT NULL,
    DischargeDateTime datetime2(0) NULL,       -- NULL = still in hospital
    AdmissionType     varchar(20)  NULL,
    DiagnosisGroup    nvarchar(60) NULL,
    SourceFile        varchar(60)  NULL
);

CREATE TABLE landing.Charge (
    ChargeID    varchar(12)  NOT NULL,
    AdmissionID varchar(12)  NOT NULL,
    ServiceDate date         NOT NULL,
    TariffCode  varchar(10)  NOT NULL,
    Quantity    decimal(9,2) NOT NULL,
    CapturedBy  varchar(30)  NULL,
    SourceFile  varchar(60)  NULL
);

CREATE TABLE landing.Payment (
    PaymentID     varchar(12)   NOT NULL,
    AdmissionID   varchar(12)   NOT NULL,
    PaymentDate   date          NOT NULL,
    PayerType     varchar(10)   NOT NULL,      -- Funder or Patient
    PaymentMethod varchar(20)   NULL,
    Amount        decimal(12,2) NOT NULL,
    SourceFile    varchar(60)   NULL
);
GO
