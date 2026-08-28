// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.architecture;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.fields;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static org.assertj.core.api.Assertions.assertThat;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.lang.ArchRule;
import com.tngtech.archunit.library.Architectures;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * The half of the layering rules Maven cannot express.
 *
 * <p>The other half is structural: engine-domain and engine-application declare no framework
 * dependencies, so importing Spring into them fails the build at the enforcer rather than
 * relying on a reviewer noticing. These rules cover direction and annotation use, which the
 * module graph does not see.
 *
 * <p>Written as plain JUnit tests calling {@code check} rather than with {@code @ArchTest}
 * fields on purpose. The field style depends on ArchUnit's own JUnit engine being selected, and
 * when it is not, the class is still collected, still passes, and reports zero tests — a suite
 * that guards nothing while looking green. Explicit calls cannot do that.
 */
class HexagonalArchitectureTest {

    private static JavaClasses engineClasses;

    @BeforeAll
    static void importEngineClasses() {
        engineClasses = new ClassFileImporter()
                .withImportOption(new ImportOption.DoNotIncludeTests())
                .importPackages("io.ludus");

        // The sibling modules arrive here as jars. If they are ever excluded from the import,
        // every rule below passes vacuously, so assert there is something real to analyse.
        assertThat(engineClasses).as("classes analysed").hasSizeGreaterThan(3);
        assertThat(engineClasses.stream().map(c -> c.getPackageName()))
                .as("all engine layers must be on the analysed classpath")
                .anyMatch(p -> p.startsWith("io.ludus.domain"))
                .anyMatch(p -> p.startsWith("io.ludus.application"))
                .anyMatch(p -> p.startsWith("io.ludus.adapter"));

        // Every rule below is declared allowEmptyShould(true), so a rule about a package with no
        // classes in it passes without checking anything. That was the honest position while the
        // application layer was empty. It is not any more, and this assertion is what stops the
        // suite quietly returning to it if an outbound port is ever moved or renamed away.
        assertThat(engineClasses.stream().map(c -> c.getPackageName()))
                .as("outbound ports must exist for the port rule to mean anything")
                .anyMatch(p -> p.startsWith("io.ludus.application") && p.endsWith("port.out"));
    }

    @Test
    void layers_depend_inwards_only() {
        ArchRule rule = Architectures.layeredArchitecture()
                .consideringOnlyDependenciesInLayers()
                .layer("Domain").definedBy("io.ludus.domain..")
                .layer("Application").definedBy("io.ludus.application..")
                .layer("Adapters").definedBy("io.ludus.adapter..")
                .layer("Bootstrap").definedBy("io.ludus", "io.ludus.config..")
                .whereLayer("Bootstrap").mayNotBeAccessedByAnyLayer()
                .whereLayer("Adapters").mayOnlyBeAccessedByLayers("Bootstrap")
                .whereLayer("Application").mayOnlyBeAccessedByLayers("Adapters", "Bootstrap")
                .allowEmptyShould(true);

        rule.check(engineClasses);
    }

    @Test
    void domain_does_not_know_about_anything_outside_itself() {
        noClasses().that().resideInAPackage("io.ludus.domain..")
                .should().dependOnClassesThat()
                .resideInAnyPackage("io.ludus.application..", "io.ludus.adapter..")
                .allowEmptyShould(true)
                .check(engineClasses);
    }

    @Test
    void application_does_not_know_about_adapters() {
        noClasses().that().resideInAPackage("io.ludus.application..")
                .should().dependOnClassesThat().resideInAPackage("io.ludus.adapter..")
                .allowEmptyShould(true)
                .check(engineClasses);
    }

    /**
     * A domain type carrying a persistence or serialization annotation has quietly become a
     * storage or wire format, and can no longer change without breaking one of them.
     */
    @Test
    void domain_and_application_carry_no_framework_types() {
        noClasses().that().resideInAnyPackage("io.ludus.domain..", "io.ludus.application..")
                .should().dependOnClassesThat()
                .resideInAnyPackage(
                        "org.springframework..",
                        "jakarta.persistence..",
                        "com.fasterxml.jackson..",
                        "org.hibernate..")
                .allowEmptyShould(true)
                .check(engineClasses);
    }

    /** Outbound ports are the seam. Implementing one outside an adapter defeats the point. */
    @Test
    void outbound_ports_are_used_only_by_the_application_and_its_adapters() {
        classes().that().resideInAPackage("..application..port.out..")
                .and().areInterfaces()
                .should().onlyHaveDependentClassesThat()
                .resideInAnyPackage("io.ludus.application..", "io.ludus.adapter..", "io.ludus.config..")
                .allowEmptyShould(true)
                .check(engineClasses);
    }

    /**
     * Field injection hides a class's real dependencies from its constructor, which is where a
     * reader looks for them, and makes the class untestable without a container.
     */
    @Test
    void no_field_injection() {
        fields()
                .should().notBeAnnotatedWith("org.springframework.beans.factory.annotation.Autowired")
                .andShould().notBeAnnotatedWith("jakarta.inject.Inject")
                .allowEmptyShould(true)
                .check(engineClasses);
    }
}
