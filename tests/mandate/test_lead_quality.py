from agentx_mandate.lead_quality import enrich_lead, is_actionable_lead, score_lead


def test_enrichment_extracts_actionable_company_role_contact_and_cited_signal() -> None:
    lead = {
        "id": "lead_1",
        "company": "Book Appointment | Galaxy Dental Clinic",
        "url": "https://galaxydental.example",
        "evidence": ["Pune dental clinic"],
    }
    page = {
        "url": "https://galaxydental.example",
        "title": "Book Appointment | Galaxy Dental Clinic",
        "markdown": (
            "# Galaxy Dental Clinic\n"
            "Dr. Asha Kulkarni and our dental team are accepting new patients in Pune.\n"
            "[Book an appointment](/contact)\n"
        ),
        "evidence": ["Dr. Asha Kulkarni and our dental team are accepting new patients in Pune."],
    }

    enriched = enrich_lead(lead, page, {"icp": "independent dental clinics", "location": "Pune"})

    assert enriched["company"] == "Galaxy Dental Clinic"
    assert enriched["contact_name"] == "Dr. Asha Kulkarni"
    assert enriched["contact_role"] == "Practice owner or clinic manager"
    assert enriched["contact_url"] == "https://galaxydental.example/contact"
    assert enriched["buying_signal_evidence"] in page["markdown"]
    assert is_actionable_lead(enriched)
    assert score_lead(enriched)[0] >= 0.8


def test_content_result_fails_closed_even_when_it_mentions_the_icp() -> None:
    enriched = enrich_lead(
        {
            "id": "bad",
            "company": "10 Best AI Lead Finders",
            "url": "https://youtube.com/watch?v=1",
            "evidence": ["A video about lead generation"],
        },
        {
            "url": "https://youtube.com/watch?v=1",
            "title": "How to Get Dental Leads",
            "markdown": "Contact dentists and book appointments.",
            "evidence": ["Contact dentists and book appointments."],
        },
        {"icp": "independent dental clinics", "location": "Pune"},
    )

    assert enriched["actionable"] is False
    assert not is_actionable_lead(enriched)
    assert score_lead(enriched)[0] == 0.0


def test_official_appointment_page_uses_clinic_name_and_whatsapp_contact() -> None:
    enriched = enrich_lead(
        {
            "id": "smile",
            "company": "Appointment Booking - Smile Inn Dental Clinic - Pune",
            "url": "https://smileinn.example/appointment-booking/",
            "evidence": ["official website"],
        },
        {
            "url": "https://smileinn.example/appointment-booking/",
            "title": "Appointment Booking - Smile Inn Dental Clinic - Pune",
            "markdown": (
                "### Appointment booking\n"
                "Smile-Inn Dental clinic introduces teleconsulting for its patients.\n"
                "[WhatsApp: 9420065036](https://wa.me/919420065036)\n"
                "Dr. Anjali Srinivasan leads the dental team."
            ),
            "evidence": ["Smile-Inn Dental clinic introduces teleconsulting for its patients."],
        },
        {"icp": "independent dental clinics", "location": "Pune"},
    )

    assert enriched["company"] == "Smile Inn Dental Clinic"
    assert enriched["contact_name"] == "Dr. Anjali Srinivasan"
    assert enriched["contact_url"] == "https://wa.me/919420065036"
    assert enriched["buying_signal"] == "Smile-Inn Dental clinic introduces teleconsulting for its patients."
    assert is_actionable_lead(enriched)


def test_agency_page_uses_growth_signal_and_real_contact_path() -> None:
    enriched = enrich_lead(
        {
            "id": "agency",
            "company": "Belkins - B2B Lead Generation Agency",
            "url": "https://belkins.example/",
            "evidence": ["official website"],
        },
        {
            "url": "https://belkins.example/",
            "title": "Belkins - B2B Lead Generation Agency",
            "markdown": (
                "# Belkins\n"
                "Our appointment setting service helps B2B teams grow their sales pipeline.\n"
                "[Book a call](/contact-us)\n"
            ),
            "evidence": ["Our appointment setting service helps B2B teams grow their sales pipeline."],
        },
        {"icp": "founders and agencies buying an AI lead-finder", "location": "United States"},
    )

    assert enriched["company"] == "Belkins"
    assert enriched["contact_role"] == "Founder or growth lead"
    assert enriched["contact_url"] == "https://belkins.example/contact-us"
    assert "sales pipeline" in str(enriched["buying_signal"])
    assert is_actionable_lead(enriched)


def test_case_study_with_booked_in_label_is_not_mistaken_for_contact_cta() -> None:
    enriched = enrich_lead(
        {
            "id": "agency",
            "company": "Belkins - B2B Lead Generation Agency",
            "url": "https://belkins.example/",
            "evidence": ["official website"],
        },
        {
            "url": "https://belkins.example/",
            "title": "Belkins - B2B Lead Generation Agency",
            "markdown": (
                "With personalized appointment setting, prospects attend demo calls.\n"
                "[145 Calls Booked in 9 Months](/case-studies/customer)\n"
                "Book a call"
            ),
            "evidence": ["With personalized appointment setting, prospects attend demo calls."],
        },
        {"icp": "founders and agencies buying an AI lead-finder"},
    )

    assert enriched["contact_url"] == "https://belkins.example/"
